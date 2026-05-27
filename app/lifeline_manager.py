from app.database import Database
from app import config


class LifelineManager:
    """Manages lifeline earning and consumption.

    Rules
    -----
    * A lifeline is earned for every 10 weekly points *above* the weekly target.
    * Lifelines are capped at MAX_LIFELINES (3).
    * Consuming a lifeline decrements the count.
    * Award logic: every time weekly points increase, recalculate how many
      lifelines the user *should* have.  If the recalculated value is higher
      than the stored count, the difference is awarded.
    """

    def __init__(self, db: Database):
        self._db = db

    def check_and_award(self) -> int:
        """Recalculate lifeline entitlement and award new ones.

        Returns the number of lifelines *newly awarded* (0 if none).
        """
        weekly_points = self._db.get_weekly_points()
        target = self._db.get_weekly_target()

        should_have = min(config.MAX_LIFELINES,
                          max(0, (weekly_points - target) // 10))
        current = self._db.get_lifelines()

        if should_have > current:
            award = should_have - current
            self._db.set_lifelines(should_have)
            return award
        return 0

    def consume(self) -> bool:
        """Try to consume one lifeline.

        Returns True if a lifeline was used, False if none available.
        """
        return self._db.consume_lifeline()

    def get_lifelines(self) -> int:
        return self._db.get_lifelines()
