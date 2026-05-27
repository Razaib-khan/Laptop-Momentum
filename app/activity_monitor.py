import time
import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from app import config
from app.database import Database
from app.input_tracker import InputTracker
from app.streak_manager import StreakManager
from app.points_manager import PointsManager
from app.lifeline_manager import LifelineManager
from app.notification_manager import NotificationManager

logger = logging.getLogger(__name__)


class ActivityMonitor(QObject):
    """Central coordinator that drives the entire application.

    Runs a 10-second QTimer on the Qt main thread.  On each tick it:
      * Detects sleep/wake and replays missed day boundaries.
      * Checks for the 04:00 day boundary and finalises the previous day.
      * Checks for the Monday 04:00 week boundary and resets weekly totals.
      * Polls the InputTracker and accrues active seconds.
      * Periodically checkpoints to the database.
      * Sends streak-risk notifications after 21:00.
    """

    # Emitted whenever the monitor has fresh data so UI elements can refresh.
    state_updated = Signal(dict)

    def __init__(self, db: Database, notifications: NotificationManager):
        super().__init__()
        self._db = db
        self._notifications = notifications

        # Sub-modules
        self._input_tracker = InputTracker(idle_timeout=config.IDLE_TIMEOUT_SECONDS)
        self._streak_mgr = StreakManager(db)
        self._points_mgr = PointsManager(db)
        self._lifeline_mgr = LifelineManager(db)

        # Timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        # In-memory counters for the *current* day.
        self._today_key = config.get_day_key()
        existing = self._db.get_daily_data(self._today_key)
        self._today_active_seconds = existing["active_seconds"]

        # Tick accounting (used to detect sleep / missed ticks).
        self._last_tick_time = time.time()
        self._tick_count = 0

        # One-shot notification guards.
        self._weekly_target_notified_this_week = False
        self._streak_risk_notified_today = False
        self._streak_threshold_notified_today = False
        self._point_threshold_notified_today = False

        # Total lifelines awarded in this tick series (for summary dedup).
        self._pending_lifeline_awards = 0

        # Session bonus (uninterrupted activity perk).
        self._session_seconds = 0
        self._session_bonus_block = 0
        self._session_bonus_notified = False
        self._bonus_points_today = existing.get("bonus_points", 0)

    # ------------------------------------------------------------------
    # Life-cycle
    # ------------------------------------------------------------------
    def start(self):
        """Begin tracking input and the periodic monitor loop."""
        self._input_tracker.start()

        # On startup, process any missed days (e.g. laptop was off).
        self._catch_up_missed_days()
        # The 04:00 day-boundary tick may never fire when we launch
        # after 04:00, so also check the week boundary here.
        self._check_week_boundary()
        # Rebuild weekly points from daily_stats — this recovers any
        # data that was lost by a previous buggy week-boundary reset.
        ws = self._points_mgr.get_week_start_date()
        if ws:
            self._db.recalculate_weekly_points(ws)

        self._timer.start(config.TICK_INTERVAL_SECONDS * 1000)
        logger.info("ActivityMonitor started (day=%s)", self._today_key)

    def stop(self):
        self._timer.stop()
        self._input_tracker.stop()
        # Final checkpoint to DB.
        self._db.set_daily_seconds(self._today_key, self._today_active_seconds)
        self._db.set_daily_bonus_points(self._today_key, self._bonus_points_today)
        logger.info("ActivityMonitor stopped")

    # ------------------------------------------------------------------
    # Public helpers for the UI layer
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        """Return a snapshot of current stats for the tray / dashboard.

        The streak values show what the streak *will be* once the current day is
        finalised at the 4 AM boundary, so the user sees real-time feedback.
        """
        state = self._db.get_app_state()
        today_minutes = self._today_active_seconds // 60
        recent = self._db.get_recent_events(10)

        current_streak = state["current_streak"]
        longest_streak = state["longest_streak"]

        # Provisional streak — include today if it already qualifies.
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

        today_points = self._points_mgr.calculate_daily_points(today_minutes) + self._bonus_points_today

        return {
            "current_streak":       current_streak,
            "longest_streak":       longest_streak,
            "last_streak_date":     state["last_streak_date"],
            "today_active_seconds": self._today_active_seconds,
            "today_active_minutes": today_minutes,
            "today_points":         today_points,
            "weekly_points":        state["current_week_points"] + today_points,
            "weekly_target":        state["weekly_target"],
            "lifelines":            state["lifelines"],
            "week_start_date":      state["week_start_date"],
            "highest_uptime_date":  highest["date"] if highest else None,
            "highest_uptime_seconds": highest["active_seconds"] if highest else 0,
            "is_active":            self._input_tracker.is_active(),
            "recent_events":        recent,
        }

    def refresh_state(self):
        """Force a state emission (e.g. after a user changes a setting)."""
        self._emit_state()

    # ------------------------------------------------------------------
    # Timer tick
    # ------------------------------------------------------------------
    def _on_tick(self):
        now = time.time()
        elapsed = now - self._last_tick_time
        self._last_tick_time = now
        self._tick_count += 1

        # 1. Detect sleep/wake – if we missed more than one tick interval
        #    the machine was probably asleep.  Replay any day-boundaries that
        #    should have fired while we were off.
        if elapsed > config.TICK_INTERVAL_SECONDS * 3:
            self._check_week_boundary()
            self._catch_up_missed_days()
            self._session_seconds = 0
            self._session_bonus_block = 0
            self._session_bonus_notified = False

        # 2. Day boundary  (4 AM)
        current_day = config.get_day_key()
        if current_day != self._today_key:
            self._finalize_day(self._today_key)
            self._today_key = current_day
            daily = self._db.get_daily_data(current_day)
            self._today_active_seconds = daily["active_seconds"]
            self._bonus_points_today = daily.get("bonus_points", 0)
            self._session_seconds = 0
            self._session_bonus_block = 0
            self._session_bonus_notified = False
            self._streak_risk_notified_today = False
            self._streak_threshold_notified_today = False
            self._point_threshold_notified_today = False
            logger.info("Day boundary crossed — now on %s", current_day)

            # 2a. Week boundary (Monday)
            self._check_week_boundary()

        # 3. Accrue active seconds
        if self._input_tracker.is_active(now):
            self._today_active_seconds += config.TICK_INTERVAL_SECONDS
            self._db.add_daily_seconds(current_day, config.TICK_INTERVAL_SECONDS)

            # 3a. Session bonus (uninterrupted activity perk).
            self._session_seconds += config.TICK_INTERVAL_SECONDS
            if self._session_seconds >= config.BONUS_SESSION_MIN_SECONDS:
                bonus_blocks = (self._session_seconds - config.BONUS_SESSION_MIN_SECONDS) // config.BONUS_INTERVAL_SECONDS
                if bonus_blocks > self._session_bonus_block:
                    newly_awarded = bonus_blocks - self._session_bonus_block
                    self._bonus_points_today += newly_awarded
                    self._session_bonus_block = bonus_blocks
                    if not self._session_bonus_notified:
                        self._notifications.bonus_session_started()
                        self._db.add_event("session_bonus",
                                           "Session bonus started — 3 pts per 2 min")
                        self._session_bonus_notified = True
        else:
            # Idle — reset session.
            self._session_seconds = 0
            self._session_bonus_block = 0
            self._session_bonus_notified = False

        # 4. Checkpoint to DB every 6 ticks (≈ 1 minute).
        if self._tick_count % 6 == 0:
            self._db.set_daily_seconds(current_day, self._today_active_seconds)
            self._db.set_daily_bonus_points(current_day, self._bonus_points_today)

        # 5. Real-time milestone notifications (fire once per threshold).
        today_minutes = self._today_active_seconds // 60

        if not self._streak_threshold_notified_today:
            if today_minutes >= config.STREAK_MINIMUM_MINUTES:
                self._notifications.streak_safe(today_minutes)
                self._db.add_event("streak_safe",
                                   f"Daily minimum reached — {today_minutes} active minutes")
                self._streak_threshold_notified_today = True

        if not self._point_threshold_notified_today:
            if today_minutes >= config.POINTS_THRESHOLD_MINUTES:
                self._notifications.point_earning_started()
                pts = today_minutes - config.POINTS_THRESHOLD_MINUTES
                self._db.add_event("point_earning",
                                   f"Point earning started — {today_minutes} min, earned {pts} pt{'s' if pts != 1 else ''} so far")
                self._point_threshold_notified_today = True

        # 6. Streak risk notification (once per day after 21:00).
        if not self._streak_risk_notified_today:
            current_hour = datetime.now().hour
            if current_hour >= config.STREAK_RISK_NOTIFICATION_HOUR:
                active_minutes = self._today_active_seconds // 60
                if active_minutes < config.STREAK_MINIMUM_MINUTES:
                    streak = self._streak_mgr.get_current_streak()
                    if streak > 0:
                        self._notifications.streak_at_risk()
                        self._db.add_event("streak_risk",
                                           f"Streak at risk — only {active_minutes} active minutes today")
                self._streak_risk_notified_today = True

        # 6. Emit updated state.
        self._emit_state()

    # ------------------------------------------------------------------
    # Missed-day catch-up (startup / wake-from-sleep)
    # ------------------------------------------------------------------
    def _catch_up_missed_days(self):
        """Walk from the last-finalized day up to *yesterday* and finalize
        any days the app missed (e.g. laptop was off)."""
        today = config.get_day_key()
        last_finalized = self._db.get_setting("last_finalized_date")

        if not last_finalized:
            # First-ever finalization. If yesterday has data (e.g. the app
            # started after 4 AM so the day-boundary tick never fired), go
            # ahead and finalize it now.
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
            # Skip days already finalized.
            finalized_marker = self._db.get_setting(f"finalized_{nxt}")
            if not finalized_marker:
                self._finalize_day(nxt)
            cursor = nxt

        # Ensure today's counters are current.
        self._today_key = today
        today_data = self._db.get_daily_data(today)
        self._today_active_seconds = today_data["active_seconds"]
        self._bonus_points_today = today_data.get("bonus_points", 0)
        self._session_seconds = 0
        self._session_bonus_block = 0
        self._session_bonus_notified = False
        self._streak_risk_notified_today = False

    # ------------------------------------------------------------------
    # Day finalization
    # ------------------------------------------------------------------
    def _finalize_day(self, date_key: str):
        """Process a completed day bucket: calculate points, update streak,
        award / consume lifelines, and send notifications."""
        daily = self._db.get_daily_data(date_key)
        active_seconds = daily["active_seconds"]
        active_minutes = active_seconds // 60
        is_streak_day = self._streak_mgr.qualifies_as_streak_day(active_minutes)
        base_points = self._points_mgr.calculate_daily_points(active_minutes)
        bonus_points = daily.get("bonus_points", 0)
        daily_points = base_points + bonus_points

        # Save raw data (overwrites any partial checkpoint).
        self._db.save_daily_stats(date_key, active_seconds, daily_points, is_streak_day, bonus_points)

        logger.info("Finalizing %s: %d sec, %d min, streak_day=%s, points=%d",
                    date_key, active_seconds, active_minutes, is_streak_day, daily_points)

        streak = self._streak_mgr.get_current_streak()

        if is_streak_day:
            # ----- Streak day -----
            self._streak_mgr.record_streak_day(date_key)
            self._db.add_event("streak_day", f"Streak day on {date_key} ({active_minutes} min)")

            if daily_points > 0:
                self._points_mgr.add_daily_points(daily_points)
                weekly_total = self._points_mgr.get_weekly_points()
                self._notifications.points_gained(daily_points, weekly_total)
                self._db.add_event("points", f"+{daily_points} points on {date_key}")

                # Check / award lifelines based on the new weekly total.
                awarded = self._lifeline_mgr.check_and_award()
                if awarded > 0:
                    lifelines = self._lifeline_mgr.get_lifelines()
                    self._notifications.lifeline_earned(lifelines)
                    self._db.add_event("lifeline_earned",
                                       f"Earned {awarded} lifeline(s) — now have {lifelines}")

                # Weekly target reached notification (once per week).
                if (not self._weekly_target_notified_this_week
                        and weekly_total >= self._points_mgr.get_weekly_target()):
                    self._notifications.weekly_target_reached(
                        weekly_total, self._points_mgr.get_weekly_target())
                    self._db.add_event("target_reached",
                                       f"Weekly target reached: {weekly_total} pts")
                    self._weekly_target_notified_this_week = True

        else:
            # ----- Not a streak day -----
            if streak > 0:
                # Try to save with a lifeline.
                if self._lifeline_mgr.consume():
                    remaining = self._lifeline_mgr.get_lifelines()
                    self._notifications.streak_saved()
                    self._notifications.lifeline_used(remaining)
                    self._db.add_event("lifeline_used",
                                       f"Lifeline saved streak on {date_key} ({remaining} left)")
                else:
                    # Streak breaks.
                    self._streak_mgr.break_streak()
                    self._db.add_event("streak_broken",
                                       f"Streak broken on {date_key} — no lifelines")
                    logger.info("Streak broken on %s", date_key)

        # Mark this day as finalised so startup catch-up skips it.
        self._db.set_setting("last_finalized_date", date_key)
        self._db.set_setting(f"finalized_{date_key}", "1")

    # ------------------------------------------------------------------
    # Week boundary
    # ------------------------------------------------------------------
    def _check_week_boundary(self):
        """If the Monday 04:00 week boundary has passed, reset weekly
        counters and send a summary notification."""
        current_week = config.get_week_key()
        stored_week = self._points_mgr.get_week_start_date()

        if stored_week is None:
            # First ever run — seed the week start date and set initial
            # target, but do NOT reset points (there may be points from
            # today's catch-up that belong to this very week).
            self._points_mgr.set_week_start_date(current_week)
            # Rebuild the weekly total from daily_stats — this recovers
            # points that a previous (buggy) build may have zeroed.
            self._db.recalculate_weekly_points(current_week)
            streak = self._streak_mgr.get_current_streak()
            new_target = self._points_mgr.calculate_auto_target(streak)
            self._points_mgr.set_weekly_target(new_target)
            self._db.add_event("settings",
                               f"Weekly target auto-set to {new_target}")
            self._weekly_target_notified_this_week = False
            logger.info("Week boundary seeded — week=%s, target=%d",
                        current_week, new_target)
            return

        if current_week != stored_week:
            # Final summary for the completed week.
            old_points = self._points_mgr.get_weekly_points()
            old_streak = self._streak_mgr.get_current_streak()
            old_lifelines = self._lifeline_mgr.get_lifelines()
            self._notifications.weekly_summary(old_streak, old_points, old_lifelines)
            self._db.add_event("week_summary",
                               f"Week ended: streak={old_streak}, points={old_points}")

            # Recalculate the weekly target based on recent performance.
            streak = self._streak_mgr.get_current_streak()
            new_target = self._points_mgr.calculate_auto_target(streak)
            self._points_mgr.set_weekly_target(new_target)
            self._db.add_event("settings",
                               f"Weekly target auto-set to {new_target}")

            self._points_mgr.reset_weekly(current_week)
            self._weekly_target_notified_this_week = False
            logger.info("Week boundary — new week starts %s, target=%d",
                        current_week, new_target)

    # ------------------------------------------------------------------
    # State emission
    # ------------------------------------------------------------------
    def _emit_state(self):
        """Emit the state_updated signal so any connected UI refreshes."""
        self.state_updated.emit(self.get_state())
