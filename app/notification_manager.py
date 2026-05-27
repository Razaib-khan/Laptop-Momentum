import logging

from PySide6.QtWidgets import QSystemTrayIcon

from app import config

logger = logging.getLogger(__name__)


class NotificationManager:
    """Sends desktop notifications via the system tray icon.

    Every method catches exceptions so a failed notification never crashes the
    app.  Respects the *notifications enabled* toggle.
    """

    def __init__(self, tray_icon: QSystemTrayIcon):
        self._tray = tray_icon
        self._enabled = True

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------
    def _notify(self, title: str, message: str,
                icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.Information,
                duration: int = config.NOTIFICATION_DURATION_MS):
        if not self._enabled:
            return
        try:
            self._tray.showMessage(title, message, icon, duration)
        except Exception as exc:
            logger.warning("Notification failed: %s", exc)

    # ------------------------------------------------------------------
    # Notification types
    # ------------------------------------------------------------------
    def streak_safe(self, minutes: int):
        self._notify("Streak Safe",
                     f"Active for {minutes} min today — your streak is secure!")

    def point_earning_started(self):
        self._notify("Now Earning Points",
                     "You passed 10 active minutes. "
                     "Every additional minute earns 1 point!")

    def streak_saved(self):
        self._notify("Streak Saved",
                     "A lifeline kept your streak alive today.")

    def streak_at_risk(self):
        self._notify("Streak at Risk",
                     "Less than 2 active minutes today. Open your laptop "
                     "and do some work to keep your streak going!")

    def points_gained(self, points: int, weekly_total: int):
        self._notify("Points Earned",
                     f"+{points} point{'s' if points != 1 else ''} today.  "
                     f"Weekly total: {weekly_total}.")

    def lifeline_earned(self, lifelines: int):
        self._notify("Lifeline Earned",
                     f"You now have {lifelines} lifeline{'s' if lifelines != 1 else ''} "
                     f"available.")

    def lifeline_used(self, remaining: int):
        self._notify("Lifeline Used",
                     f"A lifeline was consumed to protect your streak.  "
                     f"{remaining} remaining.")

    def weekly_target_reached(self, points: int, target: int):
        self._notify("Weekly Target Reached",
                     f"You hit {points}/{target} points this week!")

    def weekly_summary(self, streak: int, points: int, lifelines: int):
        self._notify("Weekly Summary",
                     f"Streak: {streak} days  |  Points: {points}  |  "
                     f"Lifelines: {lifelines}")

    def bonus_session_started(self):
        self._notify("Session Bonus Active",
                     "30 min of uninterrupted activity! "
                     "Every 2 minutes now earns 3 points instead of 2.")
