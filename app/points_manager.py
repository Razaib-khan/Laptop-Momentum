from app.database import Database
import app.config as config


class PointsManager:
    """Calculates and persists daily and weekly points.

    Rules
    -----
    * Points are earned on active minutes *above* POINTS_THRESHOLD_MINUTES (10).
    * Points == max(0, active_minutes - POINTS_THRESHOLD_MINUTES).
    * Points are separate from streak survival — you can earn points on any day
      regardless of whether it qualifies as a streak day.
    * Weekly points accumulate across the current week (Mon 04:00 → next Mon 03:59).
    * The weekly target is recalculated automatically at each week boundary based
      on recent performance, current streak, and momentum.
    """

    def __init__(self, db: Database):
        self._db = db

    def calculate_daily_points(self, active_minutes: int) -> int:
        return max(0, active_minutes - config.POINTS_THRESHOLD_MINUTES)

    def add_daily_points(self, points: int):
        """Add points to the running weekly total."""
        self._db.add_weekly_points(points)

    def get_weekly_points(self) -> int:
        return self._db.get_weekly_points()

    def get_weekly_target(self) -> int:
        return self._db.get_weekly_target()

    def set_weekly_target(self, target: int):
        self._db.set_weekly_target(target)

    def reset_weekly(self, week_key: str):
        self._db.reset_weekly_points()
        self._db.set_week_start_date(week_key)

    def get_week_start_date(self) -> str | None:
        return self._db.get_app_state().get("week_start_date")

    # ------------------------------------------------------------------
    # Adaptive target calculation
    # ------------------------------------------------------------------
    def calculate_auto_target(self, current_streak: int) -> int:
        """Derive a weekly point target based on the last 4 weeks, streak,
        and momentum, with built-in difficulty reduction after weak weeks
        so the system stays challenging without causing burnout."""

        weekly_history = self._db.get_weekly_point_totals(4)
        last_target = self.get_weekly_target()

        # 1. Base = average of available weeks, else default.
        if weekly_history and any(p > 0 for p in weekly_history):
            base = sum(weekly_history) / len(weekly_history)
        else:
            base = float(config.DEFAULT_WEEKLY_TARGET)

        # 2. Streak bonus: +5 per streak day, capped at +50.
        streak_bonus = min(current_streak * 5, 50)

        # 3. Momentum: if the most recent complete week beat its target,
        #    add 10 % of the excess.
        momentum_bonus = 0
        last_complete = weekly_history[-1] if len(weekly_history) >= 1 else 0
        if last_complete >= last_target:
            momentum_bonus = int((last_complete - last_target) * 0.1)

        # 4. Weak-week reduction: if the last week was below 50 % of its
        #    target, reduce the new target by 10 % to ease recovery.
        weak_reduction = 0
        if last_complete < last_target * 0.5 and last_target > 100:
            weak_reduction = int(last_target * 0.1)

        target = int(base + streak_bonus + momentum_bonus - weak_reduction)
        return max(100, min(target, 2000))
