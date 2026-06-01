import sqlite3
import threading
from datetime import datetime
from typing import Any

import app.config as config


class Database:
    """Thread-safe SQLite wrapper for Laptop Momentum.

    Every public write method acquires a re-entrant lock so the app can safely
    read/write from the Qt main thread and startup code without corruption.
    """

    def __init__(self, db_path: str):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=3000")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _init_schema(self):
        with self._lock:
            cur = self._conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date            TEXT PRIMARY KEY,
                    active_seconds  INTEGER NOT NULL DEFAULT 0,
                    points          INTEGER NOT NULL DEFAULT 0,
                    is_streak_day   INTEGER NOT NULL DEFAULT 0
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    id                  INTEGER PRIMARY KEY CHECK (id = 1),
                    current_streak      INTEGER NOT NULL DEFAULT 0,
                    longest_streak      INTEGER NOT NULL DEFAULT 0,
                    last_streak_date    TEXT,
                    current_week_points INTEGER NOT NULL DEFAULT 0,
                    week_start_date     TEXT,
                    lifelines           INTEGER NOT NULL DEFAULT 0,
                    weekly_target       INTEGER NOT NULL DEFAULT 500
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    event_type  TEXT    NOT NULL,
                    message     TEXT    NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # Migrations for existing databases.
            cols = [r["name"] for r in self._conn.execute("PRAGMA table_info(daily_stats)")]
            if "bonus_points" not in cols:
                self._conn.execute("ALTER TABLE daily_stats ADD COLUMN bonus_points INTEGER NOT NULL DEFAULT 0")
            if "effective_seconds" not in cols:
                self._conn.execute("ALTER TABLE daily_stats ADD COLUMN effective_seconds INTEGER NOT NULL DEFAULT 0")

            # Guarantee the singleton app_state row exists.
            cur = self._conn.execute("SELECT COUNT(*) FROM app_state")
            if cur.fetchone()[0] == 0:
                self._conn.execute("INSERT INTO app_state (id) VALUES (1)")
            self._conn.commit()

    # ------------------------------------------------------------------
    # Daily stats
    # ------------------------------------------------------------------
    def get_daily_data(self, date_key: str) -> dict[str, Any]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM daily_stats WHERE date = ?", (date_key,)
            )
            row = cur.fetchone()
            if row is None:
                return {"date": date_key, "active_seconds": 0, "points": 0,
                        "is_streak_day": False, "bonus_points": 0,
                        "effective_seconds": 0}
            return dict(row)

    def add_daily_seconds(self, date_key: str, seconds: int):
        with self._lock:
            self._conn.execute("""
                INSERT INTO daily_stats (date, active_seconds, points, is_streak_day)
                VALUES (?, ?, 0, 0)
                ON CONFLICT(date) DO UPDATE SET
                    active_seconds = active_seconds + ?
            """, (date_key, seconds, seconds))
            self._conn.commit()

    def set_daily_seconds(self, date_key: str, seconds: int):
        with self._lock:
            self._conn.execute("""
                INSERT INTO daily_stats (date, active_seconds, points, is_streak_day)
                VALUES (?, ?, 0, 0)
                ON CONFLICT(date) DO UPDATE SET
                    active_seconds = ?
            """, (date_key, seconds, seconds))
            self._conn.commit()

    def set_daily_bonus_points(self, date_key: str, bonus_points: int):
        with self._lock:
            self._conn.execute("""
                INSERT INTO daily_stats (date, active_seconds, points, is_streak_day, bonus_points)
                VALUES (?, 0, 0, 0, ?)
                ON CONFLICT(date) DO UPDATE SET bonus_points = ?
            """, (date_key, bonus_points, bonus_points))
            self._conn.commit()

    def set_daily_effective_seconds(self, date_key: str, effective_seconds: int):
        with self._lock:
            self._conn.execute("""
                INSERT INTO daily_stats (date, active_seconds, points, is_streak_day, effective_seconds)
                VALUES (?, 0, 0, 0, ?)
                ON CONFLICT(date) DO UPDATE SET effective_seconds = ?
            """, (date_key, effective_seconds, effective_seconds))
            self._conn.commit()

    def save_daily_stats(self, date_key: str, active_seconds: int, points: int,
                         is_streak_day: bool, bonus_points: int = 0,
                         effective_seconds: int = 0):
        with self._lock:
            self._conn.execute("""
                INSERT INTO daily_stats (date, active_seconds, points, is_streak_day, bonus_points, effective_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    active_seconds = ?,
                    points        = ?,
                    is_streak_day = ?,
                    bonus_points  = ?,
                    effective_seconds = ?
            """, (date_key, active_seconds, points, int(is_streak_day), bonus_points, effective_seconds,
                   active_seconds, points, int(is_streak_day), bonus_points, effective_seconds))
            self._conn.commit()

    # ------------------------------------------------------------------
    # App state  (current_streak, longest_streak, last_streak_date,
    #             current_week_points, week_start_date, lifelines, weekly_target)
    # ------------------------------------------------------------------
    def get_app_state(self) -> dict[str, Any]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM app_state WHERE id = 1")
            return dict(cur.fetchone())

    def update_app_state(self, **kwargs):
        with self._lock:
            cols = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values())
            self._conn.execute(f"UPDATE app_state SET {cols} WHERE id = 1", vals)
            self._conn.commit()

    # Convenience accessors
    def get_current_streak(self) -> int:
        return self.get_app_state()["current_streak"]

    def get_longest_streak(self) -> int:
        return self.get_app_state()["longest_streak"]

    def get_weekly_points(self) -> int:
        return self.get_app_state()["current_week_points"]

    def get_weekly_target(self) -> int:
        return self.get_app_state()["weekly_target"]

    def get_lifelines(self) -> int:
        return self.get_app_state()["lifelines"]

    def set_lifelines(self, count: int):
        self.update_app_state(lifelines=count)

    def set_weekly_target(self, target: int):
        self.update_app_state(weekly_target=target)

    def add_weekly_points(self, points: int):
        with self._lock:
            self._conn.execute("""
                UPDATE app_state SET current_week_points = current_week_points + ? WHERE id = 1
            """, (points,))
            self._conn.commit()

    def reset_weekly_points(self):
        self.update_app_state(current_week_points=0)

    def recalculate_weekly_points(self, week_start: str):
        """Rebuild *current_week_points* from the daily_stats rows that fall
        within the current week.  Useful after a first-run fix recovers
        points that were incorrectly zeroed."""
        import app.config as config
        week_end = config.add_days(week_start, 6)
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(SUM(points), 0) FROM daily_stats "
                "WHERE date >= ? AND date <= ?",
                (week_start, week_end),
            )
            total = cur.fetchone()[0]
            self._conn.execute(
                "UPDATE app_state SET current_week_points = ? WHERE id = 1",
                (total,),
            )
            self._conn.commit()

    def set_week_start_date(self, week_key: str):
        self.update_app_state(week_start_date=week_key)

    def increment_streak(self, date_key: str):
        with self._lock:
            self._conn.execute("""
                UPDATE app_state
                SET current_streak = current_streak + 1,
                    last_streak_date = ?,
                    longest_streak = MAX(longest_streak, current_streak + 1)
                WHERE id = 1
            """, (date_key,))
            self._conn.commit()

    def break_streak(self):
        self.update_app_state(current_streak=0)

    def consume_lifeline(self) -> bool:
        """Decrement lifelines by one.  Allows debt (negative lifelines) up to
        LIFELINE_DEBT_LIMIT.  Returns True if a lifeline or debt slot was used."""
        with self._lock:
            state = self.get_app_state()
            lifelines = state["lifelines"]
            if lifelines > 0:
                self._conn.execute("UPDATE app_state SET lifelines = lifelines - 1 WHERE id = 1")
                self._conn.commit()
                return True
            # Allow debt: go negative up to the debt limit.
            debt = int(state.get("lifeline_debt", 0))
            if debt < config.LIFELINE_DEBT_LIMIT:
                self._conn.execute(
                    "UPDATE app_state SET lifelines = lifelines - 1 "
                    "WHERE id = 1"
                )
                self._conn.commit()
                self.set_setting("lifeline_debt", str(debt + 1))
                return True
            return False

    def get_lifeline_debt(self) -> int:
        return int(self.get_setting("lifeline_debt", "0"))

    def repay_lifeline_debt(self):
        """Pay off one debt if lifelines > 0 and debt > 0."""
        debt = self.get_lifeline_debt()
        if debt <= 0:
            return
        with self._lock:
            state = self.get_app_state()
            if state["lifelines"] > 0:
                self._conn.execute(
                    "UPDATE app_state SET lifelines = lifelines - 1 WHERE id = 1"
                )
                self.set_setting("lifeline_debt", str(debt - 1))
                self._conn.commit()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            cur = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock:
            self._conn.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
            """, (key, value, value))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Event log
    # ------------------------------------------------------------------
    def add_event(self, event_type: str, message: str):
        with self._lock:
            now = datetime.now().isoformat(sep=" ", timespec="seconds")
            self._conn.execute(
                "INSERT INTO event_log (timestamp, event_type, message) VALUES (?, ?, ?)",
                (now, event_type, message),
            )
            self._conn.commit()

    def get_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM event_log ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
            return [dict(r) for r in reversed(rows)]

    # ------------------------------------------------------------------
    # Historical queries
    # ------------------------------------------------------------------
    def get_highest_daily_uptime(self) -> dict | None:
        """Return the day with the most active_seconds ever recorded."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT date, active_seconds FROM daily_stats "
                "WHERE active_seconds > 0 "
                "ORDER BY active_seconds DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return {"date": row["date"], "active_seconds": row["active_seconds"]}
            return None

    def get_weekly_point_totals(self, num_weeks: int) -> list[int]:
        """Return total points for each of the last *num_weeks* complete weeks
        (oldest first).  Weeks that have no data return 0."""
        import app.config as config
        current_monday = config.get_week_key()
        results = []
        with self._lock:
            for i in range(num_weeks, 0, -1):
                start = config.add_days(current_monday, -(i * 7))
                end = config.add_days(start, 6)
                cur = self._conn.execute(
                    "SELECT COALESCE(SUM(points), 0) FROM daily_stats "
                    "WHERE date >= ? AND date <= ?",
                    (start, end),
                )
                results.append(cur.fetchone()[0])
        return results

    def get_total_active_seconds(self) -> int:
        """Return total active_seconds ever recorded across all days."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(SUM(active_seconds), 0) FROM daily_stats"
            )
            return cur.fetchone()[0]

    def get_weekly_points_for_week(self, week_key: str) -> int:
        """Return total points for the given week (Monday–Sunday)."""
        import app.config as config
        end = config.add_days(week_key, 6)
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(SUM(points), 0) FROM daily_stats "
                "WHERE date >= ? AND date <= ?",
                (week_key, end),
            )
            return cur.fetchone()[0]

    def get_daily_target(self) -> int:
        val = self.get_setting("daily_target")
        return int(val) if val else config.DAILY_TARGET_DEFAULT

    def set_daily_target(self, minutes: int):
        minutes = max(config.DAILY_TARGET_MIN, min(config.DAILY_TARGET_MAX, minutes))
        self.set_setting("daily_target", str(minutes))

    def add_focus_session(self, date_key: str):
        """Increment focus session counter for a day."""
        key = f"focus_sessions_{date_key}"
        current = int(self.get_setting(key, "0"))
        self.set_setting(key, str(current + 1))

    def get_focus_sessions(self, date_key: str) -> int:
        return int(self.get_setting(f"focus_sessions_{date_key}", "0"))

    def get_total_focus_sessions(self) -> int:
        """Return lifetime focus sessions."""
        total = 0
        with self._lock:
            cur = self._conn.execute(
                "SELECT SUM(CAST(value AS INTEGER)) FROM settings "
                "WHERE key LIKE 'focus_sessions_%'"
            )
            row = cur.fetchone()
            if row and row[0]:
                total = row[0]
        return total

    def unlock_achievement(self, key: str):
        self.set_setting(f"achievement_{key}", "1")

    def is_achievement_unlocked(self, key: str) -> bool:
        return self.get_setting(f"achievement_{key}") == "1"

    def get_unlocked_achievements(self) -> list[str]:
        """Return list of achievement keys that have been unlocked."""
        results = []
        for ach in config.ACHIEVEMENTS:
            if self.is_achievement_unlocked(ach["key"]):
                results.append(ach["key"])
        return results

    def get_personal_bests(self) -> dict:
        """Return a dict of personal best records."""
        bests = {}
        # Best day (most effective seconds)
        with self._lock:
            cur = self._conn.execute(
                "SELECT date, effective_seconds FROM daily_stats "
                "WHERE effective_seconds > 0 "
                "ORDER BY effective_seconds DESC LIMIT 1"
            )
            row = cur.fetchone()
            bests["best_day"] = dict(row) if row else None
            # Best week
            import app.config as cfg
            current_monday = cfg.get_week_key()
            best_week = {"points": 0, "start": None}
            for i in range(12):  # last 12 weeks
                start = cfg.add_days(current_monday, -((i + 1) * 7))
                end = cfg.add_days(start, 6)
                cur2 = self._conn.execute(
                    "SELECT COALESCE(SUM(points), 0) FROM daily_stats "
                    "WHERE date >= ? AND date <= ?",
                    (start, end),
                )
                pts = cur2.fetchone()[0]
                if pts > best_week["points"]:
                    best_week = {"points": pts, "start": start}
            bests["best_week"] = best_week if best_week["start"] else None
            # Most consecutive streak days
            state = self.get_app_state()
            bests["longest_streak"] = state["longest_streak"]
        return bests

    def get_daily_data_for_range(self, start_date: str, end_date: str) -> list[dict]:
        """Return daily_stats rows between start_date and end_date (inclusive)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM daily_stats WHERE date >= ? AND date <= ? "
                "ORDER BY date ASC",
                (start_date, end_date),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_vacation_days_used(self) -> int:
        return int(self.get_setting("vacation_days_used", "0"))

    def use_vacation_day(self) -> bool:
        """Use one vacation day slot. Returns False if at max."""
        used = self.get_vacation_days_used()
        if used >= config.VACATION_MAX_DAYS:
            return False
        self.set_setting("vacation_days_used", str(used + 1))
        return True

    def reset_vacation_days(self):
        self.set_setting("vacation_days_used", "0")

    def export_csv(self, filepath: str) -> bool:
        """Write all daily_stats to a CSV file. Returns True on success."""
        import csv
        try:
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Active Seconds", "Effective Seconds",
                                "Points", "Bonus Points", "Streak Day"])
                with self._lock:
                    cur = self._conn.execute(
                        "SELECT * FROM daily_stats ORDER BY date ASC"
                    )
                    for row in cur:
                        writer.writerow([
                            row["date"], row["active_seconds"],
                            row.get("effective_seconds", 0),
                            row["points"], row.get("bonus_points", 0),
                            "Yes" if row["is_streak_day"] else "No",
                        ])
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def reset_all(self):
        """Wipe all progress: daily stats, events, app state, and settings
        (except autostart/notification preferences)."""
        with self._lock:
            self._conn.execute("DELETE FROM daily_stats")
            self._conn.execute("DELETE FROM event_log")
            self._conn.execute("""
                UPDATE app_state SET
                    current_streak = 0,
                    longest_streak = 0,
                    last_streak_date = NULL,
                    current_week_points = 0,
                    week_start_date = NULL,
                    lifelines = 0,
                    weekly_target = 500
                WHERE id = 1
            """)
            self._conn.execute("DELETE FROM settings")
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()
