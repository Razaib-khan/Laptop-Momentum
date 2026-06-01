import logging

from PySide6.QtWidgets import QSystemTrayIcon

import app.config as config
from app.sound_manager import SoundManager


class NotificationManager:
    """Sends desktop notifications via the system tray icon.

    Every method catches exceptions so a failed notification never crashes the
    app.  Respects the *notifications enabled* toggle.
    """

    def __init__(self, tray_icon: QSystemTrayIcon):
        self._tray = tray_icon
        self._enabled = True
        self._sound_mgr: SoundManager | None = None

    def set_sound_manager(self, mgr: SoundManager):
        self._sound_mgr = mgr

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

    def _play_sound(self, kind: str):
        if self._sound_mgr:
            try:
                self._sound_mgr.play(kind)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Notification types
    # ------------------------------------------------------------------
    def streak_safe(self, minutes: int):
        self._notify("Streak Safe",
                     f"Active for {minutes} min today — your streak is secure!")
        self._play_sound("milestone")

    def point_earning_started(self):
        self._notify("Now Earning Points",
                     "You passed 10 active minutes. "
                     "Every additional minute earns 1 point!")

    def points_gained(self, points: int, weekly_total: int):
        self._notify("Points Earned",
                     f"+{points} point{'s' if points != 1 else ''} today.  "
                     f"Weekly total: {weekly_total}.")
        self._play_sound("bonus")

    def weekly_target_reached(self, points: int, target: int):
        self._notify("Weekly Target Reached",
                     f"You hit {points}/{target} points this week!")
        self._play_sound("milestone")

    def achievement_unlocked(self, label: str, desc: str):
        self._notify(f"Achievement Unlocked: {label}",
                     desc,
                     icon=QSystemTrayIcon.Information,
                     duration=8000)
        self._play_sound("achievement")

    def daily_target_reached(self, minutes: int, target: int):
        self._notify("Daily Target Reached",
                     f"{minutes} active minutes today — you hit your {target}-minute goal!")

    def mystery_bonus(self, points: int):
        self._notify("Morning Bonus",
                     f"+{points} bonus point{'s' if points != 1 else ''} "
                     f"to start your day!")

    def streak_at_risk(self):
        self._notify("Streak at Risk",
                     f"Only a few active minutes today — your streak might break tonight!",
                     icon=QSystemTrayIcon.Warning)

    def bonus_session_started(self):
        self._notify("Session Bonus Active",
                     "30 min of uninterrupted activity — now earning 3 points per 2 min!")

    def streak_saved(self):
        self._notify("Streak Saved",
                     "A lifeline was used to save your streak today.")

    def lifeline_used(self, remaining: int):
        self._notify("Lifeline Used",
                     f"One lifeline consumed.  {remaining} lifeline{'s' if remaining != 1 else ''} remaining.")

    def weekly_summary(self, streak: int, points: int, lifelines: int):
        self._notify("Week Summary",
                     f"Streak: {streak} day{'s' if streak != 1 else ''}  |  "
                     f"Points: {points}  |  Lifelines: {lifelines}")

    def focus_session_completed(self, total: int):
        self._notify("Focus Session",
                     f"20 min of uninterrupted focus!  "
                     f"You've completed {total} session{'s' if total != 1 else ''}.")
