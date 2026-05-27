import sqlite3
import threading
from datetime import datetime
from typing import Any


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
            # Add bonus_points column if missing (migration for existing DBs).
            cols = [r["name"] for r in self._conn.execute("PRAGMA table_info(daily_stats)")]
            if "bonus_points" not in cols:
                self._conn.execute("ALTER TABLE daily_stats ADD COLUMN bonus_points INTEGER NOT NULL DEFAULT 0")

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
                        "is_streak_day": False, "bonus_points": 0}
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

    def save_daily_stats(self, date_key: str, active_seconds: int, points: int,
                         is_streak_day: bool, bonus_points: int = 0):
        with self._lock:
            self._conn.execute("""
                INSERT INTO daily_stats (date, active_seconds, points, is_streak_day, bonus_points)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    active_seconds = ?,
                    points        = ?,
                    is_streak_day = ?,
                    bonus_points  = ?
            """, (date_key, active_seconds, points, int(is_streak_day), bonus_points,
                   active_seconds, points, int(is_streak_day), bonus_points))
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
        from app import config
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
        """Decrement lifelines by one.  Returns True if a lifeline was available."""
        with self._lock:
            state = self.get_app_state()
            if state["lifelines"] > 0:
                self._conn.execute("UPDATE app_state SET lifelines = lifelines - 1 WHERE id = 1")
                self._conn.commit()
                return True
            return False

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
        from app import config
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

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def close(self):
        with self._lock:
            self._conn.close()
