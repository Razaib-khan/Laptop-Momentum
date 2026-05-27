from app.database import Database
from app import config


class StreakManager:
    """Handles streak increment, break, and query logic.

    Rules
    -----
    * A day qualifies as a *streak day* when active_minutes >= STREAK_MINIMUM_MINUTES.
    * On a streak day the current streak increments by one and longest_streak
      is updated if needed.
    * When a day does *not* qualify the caller may first try a lifeline (via
      LifelineManager).  Only if no lifeline is available should break_streak()
      be called.
    """

    def __init__(self, db: Database):
        self._db = db

    def record_streak_day(self, date_key: str):
        """Increment current streak, update longest streak, set last_streak_date."""
        self._db.increment_streak(date_key)

    def break_streak(self):
        """Reset current streak to zero."""
        self._db.break_streak()

    def get_current_streak(self) -> int:
        return self._db.get_current_streak()

    def get_longest_streak(self) -> int:
        return self._db.get_longest_streak()

    def get_last_streak_date(self) -> str | None:
        return self._db.get_app_state().get("last_streak_date")

    def qualifies_as_streak_day(self, active_minutes: int) -> bool:
        return active_minutes >= config.STREAK_MINIMUM_MINUTES
