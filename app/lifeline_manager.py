from app.database import Database
import app.config as config


class LifelineManager:
    """Manages lifeline earning, consumption, and debt."""

    def __init__(self, db: Database):
        self._db = db

    def check_and_award(self) -> int:
        """Recalculate lifeline entitlement and award new ones.
        Also repays any outstanding debt first."""
        weekly_points = self._db.get_weekly_points()
        target = self._db.get_weekly_target()

        should_have = min(config.MAX_LIFELINES,
                          max(0, (weekly_points - target) // 10))
        current = self._db.get_lifelines()
        debt = self._db.get_lifeline_debt()

        # Repay debt first.
        net = current
        while debt > 0 and net > 0:
            self._db.repay_lifeline_debt()
            debt -= 1
            net -= 1

        # Account for remaining debt in entitlement.
        effective_current = self._db.get_lifelines()
        if should_have > effective_current:
            award = should_have - effective_current
            self._db.set_lifelines(should_have)
            return award
        return 0

    def consume(self) -> bool:
        """Try to consume one lifeline (may go into debt)."""
        return self._db.consume_lifeline()

    def get_lifelines(self) -> int:
        return self._db.get_lifelines()

    def get_debt(self) -> int:
        return self._db.get_lifeline_debt()
