import time
import random
import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

import app.config as config
from app.database import Database
from app.input_tracker import InputTracker
from app.streak_manager import StreakManager
from app.points_manager import PointsManager
from app.lifeline_manager import LifelineManager
from app.notification_manager import NotificationManager
from app.phone_notifier import PhoneNotifier

logger = logging.getLogger(__name__)


class ActivityMonitor(QObject):
    state_updated = Signal(dict)

    def __init__(self, db: Database, notifications: NotificationManager):
        super().__init__()
        self._db = db
        self._notifications = notifications

        self._input_tracker = InputTracker(idle_timeout=config.IDLE_TIMEOUT_SECONDS)
        self._streak_mgr = StreakManager(db)
        self._points_mgr = PointsManager(db)
        self._lifeline_mgr = LifelineManager(db)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._today_key = config.get_day_key()
        existing = self._db.get_daily_data(self._today_key)
        self._today_active_seconds = existing["active_seconds"]
        self._effective_active_seconds = existing.get("effective_seconds", 0)

        self._last_tick_time = time.time()
        self._tick_count = 0

        self._weekly_target_notified_this_week = False
        self._streak_risk_notified_today = False
        self._streak_threshold_notified_today = False
        self._point_threshold_notified_today = False

        self._pending_lifeline_awards = 0

        self._session_seconds = 0
        self._session_bonus_block = 0
        self._session_bonus_notified = False
        self._bonus_points_today = existing.get("bonus_points", 0)

        self._focus_session_seconds = 0
        self._focus_session_notified = False

        self._checked_achievements: set[str] = set()

        self._phone_notifier = PhoneNotifier()
        self._last_phone_risk_check = 0.0
        self._last_heartbeat_send = 0.0

    def start(self):
        self._input_tracker.start()
        self._catch_up_missed_days()
        self._check_week_boundary()
        ws = self._points_mgr.get_week_start_date()
        if ws:
            self._db.recalculate_weekly_points(ws)
        self._timer.start(config.TICK_INTERVAL_SECONDS * 1000)
        logger.info("ActivityMonitor started (day=%s)", self._today_key)

    def stop(self):
        self._timer.stop()
        self._input_tracker.stop()
        self._db.set_daily_seconds(self._today_key, self._today_active_seconds)
        self._db.set_daily_bonus_points(self._today_key, self._bonus_points_today)
        logger.info("ActivityMonitor stopped")

    def get_state(self) -> dict:
        state = self._db.get_app_state()
        today_minutes = int(self._effective_active_seconds // 60)
        recent = self._db.get_recent_events(10)

        current_streak = state["current_streak"]
        longest_streak = state["longest_streak"]

        if self._streak_mgr.qualifies_as_streak_day(today_minutes):
            last_date = state["last_streak_date"]
            today_key = config.get_day_key()
            yesterday = config.add_days(today_key, -1)
            if last_date is None or last_date < yesterday:
                provisional = 1
            elif last_date == yesterday:
                provisional = current_streak + 1
            else:
                provisional = current_streak
            current_streak = max(current_streak, provisional)
            longest_streak = max(longest_streak, provisional)

        highest = self._db.get_highest_daily_uptime()
        total_seconds = self._db.get_total_active_seconds()
        current_day_key = config.get_day_key()

        today_points = self._points_mgr.calculate_daily_points(today_minutes) + self._bonus_points_today

        week_start = state.get("week_start_date", "")
        last_week_start = config.add_days(week_start, -7) if week_start else ""
        last_week_points = self._db.get_weekly_points_for_week(last_week_start) if last_week_start else 0

        quality = self._input_tracker.scorer.get_quality()
        if quality >= config.QUALITY_HIGH_THRESHOLD:
            quality_tier = "high"
        elif quality >= config.QUALITY_LOW_THRESHOLD:
            quality_tier = "medium"
        else:
            quality_tier = "low"

        return {
            "current_streak":          current_streak,
            "longest_streak":          longest_streak,
            "last_streak_date":        state["last_streak_date"],
            "today_active_seconds":    self._today_active_seconds,
            "effective_active_seconds": self._effective_active_seconds,
            "today_active_minutes":    today_minutes,
            "today_points":            today_points,
            "weekly_points":           state["current_week_points"] + today_points,
            "weekly_target":           state["weekly_target"],
            "lifelines":               state["lifelines"],
            "lifeline_debt":           self._db.get_lifeline_debt(),
            "week_start_date":         state["week_start_date"],
            "highest_uptime_date":     highest["date"] if highest else None,
            "highest_uptime_seconds":  highest["active_seconds"] if highest else 0,
            "is_active":               self._input_tracker.is_active(),
            "recent_events":           recent,
            "quality_score":           quality,
            "quality_tier":            quality_tier,
            "total_active_seconds":    total_seconds,
            "last_week_points":        last_week_points,
            "daily_target":            self._db.get_daily_target(),
            "focus_sessions_today":    self._db.get_focus_sessions(current_day_key),
            "total_focus_sessions":    self._db.get_total_focus_sessions(),
            "achievements":            self._db.get_unlocked_achievements(),
            "personal_bests":          self._db.get_personal_bests(),
            "vacation_mode":           self._db.get_setting("vacation_mode") == "1",
            "vacation_days_used":      self._db.get_vacation_days_used(),
            "heatmap":                 self._get_heatmap_data(),
        }

    def _get_heatmap_data(self) -> list[dict]:
        today = config.get_day_key()
        start = config.add_days(today, -48)
        rows = self._db.get_daily_data_for_range(start, today)
        known = {r["date"]: r for r in rows}
        result = []
        d = start
        while d <= today:
            if d in known:
                r = known[d]
                eff_sec = r.get("effective_seconds", r["active_seconds"])
                result.append({"date": d, "minutes": eff_sec // 60, "streak_day": bool(r["is_streak_day"])})
            else:
                result.append({"date": d, "minutes": 0, "streak_day": False})
            d = config.add_days(d, 1)
        return result

    def refresh_state(self):
        self._emit_state()

    def _on_tick(self):
        now = time.time()
        elapsed = now - self._last_tick_time
        self._last_tick_time = now
        self._tick_count += 1

        if elapsed > config.TICK_INTERVAL_SECONDS * 3:
            self._check_week_boundary()
            self._catch_up_missed_days()
            self._session_seconds = 0
            self._session_bonus_block = 0
            self._session_bonus_notified = False
            self._focus_session_seconds = 0
            self._focus_session_notified = False

        current_day = config.get_day_key()
        if current_day != self._today_key:
            self._finalize_day(self._today_key)
            self._today_key = current_day
            daily = self._db.get_daily_data(current_day)
            self._today_active_seconds = daily["active_seconds"]
            self._effective_active_seconds = daily.get("effective_seconds", 0)
            self._bonus_points_today = daily.get("bonus_points", 0)
            self._session_seconds = 0
            self._session_bonus_block = 0
            self._session_bonus_notified = False
            self._focus_session_seconds = 0
            self._focus_session_notified = False
            self._streak_risk_notified_today = False
            self._streak_threshold_notified_today = False
            self._point_threshold_notified_today = False
            self._daily_target_notified = False
            self._last_phone_risk_check = 0.0
            self._check_early_bird()
            self._check_night_owl()
            logger.info("Day boundary crossed — now on %s", current_day)
            self._check_week_boundary()

        if self._input_tracker.is_active(now):
            self._today_active_seconds += config.TICK_INTERVAL_SECONDS
            self._db.add_daily_seconds(current_day, config.TICK_INTERVAL_SECONDS)

            quality = self._input_tracker.scorer.get_quality()
            if quality >= config.QUALITY_HIGH_THRESHOLD:
                credit = 1.0
            elif quality >= config.QUALITY_LOW_THRESHOLD:
                credit = config.QUALITY_MEDIUM_FRACTION
            else:
                credit = 0.0
            self._effective_active_seconds += config.TICK_INTERVAL_SECONDS * credit

            now_hour = datetime.now().hour
            if now_hour < config.MYSTERY_BONUS_CUTOFF_HOUR:
                bonus_key = f"mystery_bonus_{current_day}"
                if self._db.get_setting(bonus_key) != "1":
                    bonus = random.randint(config.MYSTERY_BONUS_MIN, config.MYSTERY_BONUS_MAX)
                    self._bonus_points_today += bonus
                    self._db.set_setting(bonus_key, "1")
                    self._notifications.mystery_bonus(bonus)
                    self._db.add_event("mystery_bonus", f"Morning bonus: +{bonus} points")

            if random.random() < config.RANDOM_BONUS_CHANCE:
                self._bonus_points_today += 1

            self._session_seconds += config.TICK_INTERVAL_SECONDS
            if self._session_seconds >= config.BONUS_SESSION_MIN_SECONDS:
                bonus_blocks = (self._session_seconds - config.BONUS_SESSION_MIN_SECONDS) // config.BONUS_INTERVAL_SECONDS
                if bonus_blocks > self._session_bonus_block:
                    newly_awarded = bonus_blocks - self._session_bonus_block
                    self._bonus_points_today += newly_awarded
                    self._session_bonus_block = bonus_blocks
                    if not self._session_bonus_notified:
                        self._notifications.bonus_session_started()
                        self._db.add_event("session_bonus", "Session bonus started — 3 pts per 2 min")
                        self._session_bonus_notified = True

            self._focus_session_seconds += config.TICK_INTERVAL_SECONDS
            if self._focus_session_seconds >= config.FOCUS_SESSION_MIN_SECONDS and not self._focus_session_notified:
                self._db.add_focus_session(current_day)
                focus_count = self._db.get_total_focus_sessions()
                self._notifications.focus_session_completed(focus_count)
                self._db.add_event("focus_session", f"Focus session completed ({focus_count} total)")
                self._focus_session_notified = True
        else:
            self._session_seconds = 0
            self._session_bonus_block = 0
            self._session_bonus_notified = False
            self._focus_session_seconds = 0
            self._focus_session_notified = False

        if self._tick_count % 6 == 0:
            self._db.set_daily_seconds(current_day, self._today_active_seconds)
            self._db.set_daily_effective_seconds(current_day, int(self._effective_active_seconds))
            self._db.set_daily_bonus_points(current_day, self._bonus_points_today)

        today_minutes = int(self._effective_active_seconds // 60)

        if not self._streak_threshold_notified_today:
            if today_minutes >= config.STREAK_MINIMUM_MINUTES:
                self._notifications.streak_safe(today_minutes)
                self._db.add_event("streak_safe", f"Daily minimum reached — {today_minutes} effective active minutes")
                self._streak_threshold_notified_today = True

        if not self._point_threshold_notified_today:
            if today_minutes >= config.POINTS_THRESHOLD_MINUTES:
                self._notifications.point_earning_started()
                pts = today_minutes - config.POINTS_THRESHOLD_MINUTES
                self._db.add_event("point_earning",
                                   f"Point earning started — {today_minutes} effective min, earned {pts} pt{'s' if pts != 1 else ''} so far")
                self._point_threshold_notified_today = True

        # Daily target reached notification
        daily_target = self._db.get_daily_target()
        if today_minutes >= daily_target and today_minutes > 0:
            if not hasattr(self, "_daily_target_notified") or not self._daily_target_notified:
                self._notifications.daily_target_reached(today_minutes, daily_target)
                self._db.add_event("daily_target", f"Daily target reached: {today_minutes} min")
                self._daily_target_notified = True

        if not self._streak_risk_notified_today:
            current_hour = datetime.now().hour
            if current_hour >= config.STREAK_RISK_NOTIFICATION_HOUR:
                active_minutes = int(self._effective_active_seconds // 60)
                if active_minutes < config.STREAK_MINIMUM_MINUTES:
                    streak = self._streak_mgr.get_current_streak()
                    if streak > 0:
                        self._notifications.streak_at_risk()
                        self._db.add_event("streak_risk", f"Streak at risk — only {active_minutes} active minutes today")
                self._streak_risk_notified_today = True

        # Phone reminder (periodic, starts at PHONE_NOTIFIER_HOUR).
        phone_enabled = self._db.get_setting("phone_reminder_enabled") == "1"
        if phone_enabled and PhoneNotifier.is_configured():
            current_hour = datetime.now().hour
            if current_hour >= config.PHONE_NOTIFIER_HOUR:
                active_minutes = int(self._effective_active_seconds // 60)
                if active_minutes < config.STREAK_MINIMUM_MINUTES:
                    elapsed = time.time() - self._last_phone_risk_check
                    if elapsed >= config.PHONE_NOTIFIER_INTERVAL * 60:
                        streak = self._streak_mgr.get_current_streak()
                        if streak > 0:
                            msg = (f"⚠️ Streak at Risk!\n"
                                   f"Only {active_minutes} active min today "
                                   f"(need {config.STREAK_MINIMUM_MINUTES}). "
                                   f"Current streak: {streak} day{'s' if streak != 1 else ''}.")
                            PhoneNotifier.send_message(msg)
                            self._db.add_event("phone_reminder",
                                               f"Phone alert sent — {active_minutes} active min, streak={streak}")
                        self._last_phone_risk_check = time.time()

        self._send_heartbeat(active_minutes)
        self._check_achievements()
        self._emit_state()

    def _send_heartbeat(self, active_minutes: int):
        now = time.time()
        if now - self._last_heartbeat_send < config.PHONE_NOTIFIER_INTERVAL * 60:
            return
        self._last_heartbeat_send = now
        streak = self._streak_mgr.get_current_streak()
        safe = active_minutes >= config.STREAK_MINIMUM_MINUTES
        PhoneNotifier.send_heartbeat(active_minutes, safe)
        self._db.add_event("heartbeat",
                           f"Sent — {active_minutes} active min, streak_safe={safe}, streak={streak}")

    def _check_achievements(self):
        state = self._db.get_app_state()
        streak = state["current_streak"]
        longest = state["longest_streak"]

        for ach in config.ACHIEVEMENTS:
            key = ach["key"]
            if key in self._checked_achievements:
                continue
            if self._db.is_achievement_unlocked(key):
                self._checked_achievements.add(key)
                continue

            unlocked = False
            if key == "first_streak" and longest >= 7:
                unlocked = True
            elif key == "dedicated" and longest >= 30:
                unlocked = True
            elif key == "unstoppable" and longest >= 100:
                unlocked = True
            elif key == "legendary" and longest >= 365:
                unlocked = True
            elif key == "marathoner":
                total_sec = self._db.get_total_active_seconds()
                if total_sec >= 360000:
                    unlocked = True
            elif key == "centurion":
                weekly = state["current_week_points"]
                if weekly >= 1000:
                    unlocked = True
            elif key == "focus_master":
                total = self._db.get_total_focus_sessions()
                if total >= 50:
                    unlocked = True

            if unlocked:
                self._db.unlock_achievement(key)
                self._checked_achievements.add(key)
                self._notifications.achievement_unlocked(ach["label"], ach["desc"])
                self._db.add_event("achievement", f"Unlocked: {ach['label']} — {ach['desc']}")

    def _check_early_bird(self):
        key = "early_bird"
        if self._db.is_achievement_unlocked(key):
            return
        count_key = "early_bird_count"
        count = int(self._db.get_setting(count_key, "0"))
        hour = datetime.now().hour
        if 0 < hour < 8:
            self._db.set_setting(count_key, str(count + 1))
            if count + 1 >= 7:
                self._db.unlock_achievement(key)
                self._checked_achievements.add(key)
                ach = next(a for a in config.ACHIEVEMENTS if a["key"] == key)
                self._notifications.achievement_unlocked(ach["label"], ach["desc"])
                self._db.add_event("achievement", f"Unlocked: {ach['label']}")

    def _check_night_owl(self):
        key = "night_owl"
        if self._db.is_achievement_unlocked(key):
            return
        count_key = "night_owl_count"
        count = int(self._db.get_setting(count_key, "0"))
        hour = datetime.now().hour
        if hour >= 0 and hour < 4:
            self._db.set_setting(count_key, str(count + 1))
            if count + 1 >= 7:
                self._db.unlock_achievement(key)
                self._checked_achievements.add(key)
                ach = next(a for a in config.ACHIEVEMENTS if a["key"] == key)
                self._notifications.achievement_unlocked(ach["label"], ach["desc"])
                self._db.add_event("achievement", f"Unlocked: {ach['label']}")

    def _catch_up_missed_days(self):
        today = config.get_day_key()
        last_finalized = self._db.get_setting("last_finalized_date")
        if not last_finalized:
            yesterday = config.add_days(today, -1)
            daily = self._db.get_daily_data(yesterday)
            if daily["active_seconds"] > 0:
                self._finalize_day(yesterday)
            last_finalized = self._db.get_setting("last_finalized_date")
            if not last_finalized:
                return
        cursor = last_finalized
        yesterday = config.add_days(today, -1)
        while cursor < yesterday:
            nxt = config.add_days(cursor, 1)
            finalized_marker = self._db.get_setting(f"finalized_{nxt}")
            if not finalized_marker:
                self._finalize_day(nxt)
            cursor = nxt
        self._today_key = today
        today_data = self._db.get_daily_data(today)
        self._today_active_seconds = today_data["active_seconds"]
        self._effective_active_seconds = today_data.get("effective_seconds", 0)
        self._bonus_points_today = today_data.get("bonus_points", 0)
        self._session_seconds = 0
        self._session_bonus_block = 0
        self._session_bonus_notified = False
        self._focus_session_seconds = 0
        self._focus_session_notified = False
        self._streak_risk_notified_today = False

    def _finalize_day(self, date_key: str):
        daily = self._db.get_daily_data(date_key)
        active_seconds = daily["active_seconds"]
        effective_seconds = daily.get("effective_seconds", active_seconds)
        active_minutes = effective_seconds // 60
        is_streak_day = self._streak_mgr.qualifies_as_streak_day(active_minutes)
        base_points = self._points_mgr.calculate_daily_points(active_minutes)
        bonus_points = daily.get("bonus_points", 0)
        daily_points = base_points + bonus_points
        self._db.save_daily_stats(date_key, active_seconds, daily_points,
                                  is_streak_day, bonus_points, effective_seconds)
        logger.info("Finalizing %s: %d sec, %d min, streak_day=%s, points=%d",
                    date_key, active_seconds, active_minutes, is_streak_day, daily_points)
        streak = self._streak_mgr.get_current_streak()

        if is_streak_day:
            self._streak_mgr.record_streak_day(date_key)
            self._db.add_event("streak_day", f"Streak day on {date_key} ({active_minutes} min)")
            if daily_points > 0:
                self._points_mgr.add_daily_points(daily_points)
                weekly_total = self._points_mgr.get_weekly_points()
                self._notifications.points_gained(daily_points, weekly_total)
                self._db.add_event("points", f"+{daily_points} points on {date_key}")
                awarded = self._lifeline_mgr.check_and_award()
                if awarded > 0:
                    lifelines = self._lifeline_mgr.get_lifelines()
                    self._notifications.lifeline_earned(lifelines)
                    self._db.add_event("lifeline_earned", f"Earned {awarded} lifeline(s) — now have {lifelines}")
                if (not self._weekly_target_notified_this_week
                        and weekly_total >= self._points_mgr.get_weekly_target()):
                    self._notifications.weekly_target_reached(weekly_total, self._points_mgr.get_weekly_target())
                    self._db.add_event("target_reached", f"Weekly target reached: {weekly_total} pts")
                    self._weekly_target_notified_this_week = True
        else:
            if streak > 0:
                vacation_active = self._db.get_setting("vacation_mode") == "1"
                if vacation_active and self._lifeline_mgr.consume():
                    vdays = self._db.get_vacation_days_used()
                    if vdays < config.VACATION_MAX_DAYS:
                        self._db.use_vacation_day()
                        self._db.add_event("vacation", f"Vacation day on {date_key} ({vdays + 1}/{config.VACATION_MAX_DAYS})")
                        logger.info("Vacation day on %s — streak preserved", date_key)
                if self._streak_mgr.get_current_streak() == 0:
                    pass  # streak was already 0, nothing to do
                elif self._lifeline_mgr.consume():
                    remaining = self._lifeline_mgr.get_lifelines()
                    self._notifications.streak_saved()
                    self._notifications.lifeline_used(remaining)
                    self._db.add_event("lifeline_used", f"Lifeline saved streak on {date_key} ({remaining} left)")
                else:
                    freeze_key = f"freeze_used_{config.get_week_key()}"
                    freeze_used = self._db.get_setting(freeze_key)
                    if freeze_used != "1":
                        self._db.set_setting(freeze_key, "1")
                        self._db.add_event("streak_frozen", f"Streak frozen on {date_key} — day skipped without penalty")
                        logger.info("Streak frozen on %s — freeze consumed", date_key)
                    else:
                        self._streak_mgr.break_streak()
                        self._db.add_event("streak_broken", f"Streak broken on {date_key} — no lifelines")
                        logger.info("Streak broken on %s", date_key)

        self._db.set_setting("last_finalized_date", date_key)
        self._db.set_setting(f"finalized_{date_key}", "1")

    def _check_week_boundary(self):
        current_week = config.get_week_key()
        stored_week = self._points_mgr.get_week_start_date()
        if stored_week is None:
            self._db.set_week_start_date(current_week)
            self._db.recalculate_weekly_points(current_week)
            streak = self._streak_mgr.get_current_streak()
            new_target = self._points_mgr.calculate_auto_target(streak)
            self._points_mgr.set_weekly_target(new_target)
            self._db.add_event("settings", f"Weekly target auto-set to {new_target}")
            self._weekly_target_notified_this_week = False
            logger.info("Week boundary seeded — week=%s, target=%d", current_week, new_target)
            return
        if current_week != stored_week:
            old_points = self._points_mgr.get_weekly_points()
            old_streak = self._streak_mgr.get_current_streak()
            old_lifelines = self._lifeline_mgr.get_lifelines()
            self._notifications.weekly_summary(old_streak, old_points, old_lifelines)
            self._db.add_event("week_summary", f"Week ended: streak={old_streak}, points={old_points}")
            streak = self._streak_mgr.get_current_streak()
            new_target = self._points_mgr.calculate_auto_target(streak)
            self._points_mgr.set_weekly_target(new_target)
            self._db.add_event("settings", f"Weekly target auto-set to {new_target}")
            self._points_mgr.reset_weekly(current_week)
            self._weekly_target_notified_this_week = False
            # Reset vacation days at week boundary
            self._db.reset_vacation_days()
            logger.info("Week boundary — new week starts %s, target=%d", current_week, new_target)

    def _emit_state(self):
        self.state_updated.emit(self.get_state())
