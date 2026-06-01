"""Laptop Momentum — background streak & point tracker for daily laptop activity.

Usage
-----
    uv run python main.py       # run in development
    laptop-momentum.exe         # packaged release
"""
import sys
import os
import platform
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app import config
from app.database import Database
from app.notification_manager import NotificationManager
from app.sound_manager import SoundManager
from app.activity_monitor import ActivityMonitor
from app.ui.tray import TrayIcon


def _hide_console():
    """On Windows, hide the console window so the app runs silently in the
    background.  Safe to call even when launched with ``pythonw.exe`` (no-op
    because GetConsoleWindow returns NULL)."""
    try:
        if platform.system() == "Windows":
            import ctypes
            handle = ctypes.windll.kernel32.GetConsoleWindow()
            if handle:
                ctypes.windll.user32.ShowWindow(handle, 0)  # SW_HIDE
    except Exception:
        pass


def _setup_logging(data_dir: str):
    log_path = os.path.join(data_dir, "momentum.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def _global_exception_hook(exc_type, exc_value, exc_tb):
    """Log any unhandled exception and show a message box so the user knows
    something went wrong, but keep the app alive if possible."""
    import traceback
    logger = logging.getLogger("crash")
    logger.critical("Unhandled exception",
                    exc_info=(exc_type, exc_value, exc_tb))
    try:
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Laptop Momentum — Error",
                             f"An unexpected error occurred. Check the log for details.\n\n{msg[-300:]}")
    except Exception:
        pass


def main():
    # 0. Save the real executable path before anything can modify it.
    #    Used by the tray's "Restart App" action.
    import __main__
    __main__._SAVED_EXECUTABLE = sys.executable

    # 1. Install global exception hook.
    sys.excepthook = _global_exception_hook

    # 2. Hide the console window immediately on Windows.
    _hide_console()

    # 3. Ensure the data directory exists.
    data_dir = config.get_data_dir()
    os.makedirs(data_dir, exist_ok=True)

    # 4. Logging.
    _setup_logging(data_dir)
    logger = logging.getLogger("main")
    logger.info("Laptop Momentum starting — data dir: %s", data_dir)

    # 5. High-DPI support.
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 5. Create the Qt application.
    app = QApplication(sys.argv)
    app.setApplicationName("Laptop Momentum")
    app.setOrganizationName("LaptopMomentum")
    app.setQuitOnLastWindowClosed(False)  # tray-only app

    # 6. Database.
    db_path = os.path.join(data_dir, "momentum.db")
    db = Database(db_path)

    # 7. Restore notification preference.
    notifications_enabled = db.get_setting("notifications_enabled", "1") == "1"

    # 8. Build the tray icon first (must exist before notifications can fire).
    tray = TrayIcon(db)
    # Set the app-level window icon so Dashboard / dialogs use the favicon.
    app.setWindowIcon(tray.icon())

    # 9. Notification manager (attached to the tray).
    notifier = NotificationManager(tray)
    notifier.set_enabled(notifications_enabled)

    # 9b. Sound manager (plays pleasant effects for milestones).
    sound_mgr = SoundManager()
    notifier.set_sound_manager(sound_mgr)

    # 10. Activity monitor (central coordinator — needs the notifier).
    monitor = ActivityMonitor(db, notifier)

    # 11. Wire tray -> monitor (monitor needs the tray signal connection).
    tray.set_monitor(monitor)

    # 12. Start the monitor BEFORE showing the tray so all subsystems are
    #     ready before the user can interact with the icon.
    monitor.start()

    # 13. Restore notification toggle in the tray menu.
    tray._toggle_notifications_action.setChecked(notifications_enabled)
    tray._update_notification_action_text(notifications_enabled)

    # 14. Show tray icon (now everything is live).
    tray.show()

    # 15. Run the event loop.
    logger.info("Application started")
    exit_code = app.exec()

    # 16. Clean up.
    monitor.stop()
    sound_mgr.cleanup()
    db.close()
    logger.info("Application stopped")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
