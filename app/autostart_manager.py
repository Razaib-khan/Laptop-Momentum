import os
import sys
import platform
import logging

logger = logging.getLogger(__name__)


class AutostartManager:
    """Registers / unregisters the application to start on user login.

    Platform implementations
    ------------------------
    **Windows** -- writes an entry to HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    **macOS**   -- creates / removes a LaunchAgent plist (stub for future).
    **Linux**   -- creates / removes a .desktop file in ~/.config/autostart (stub).
    """

    def __init__(self):
        self._system = platform.system()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enable(self) -> bool:
        """Register the app to start at login.  Returns True on success."""
        try:
            if self._system == "Windows":
                return self._enable_windows()
            elif self._system == "Darwin":
                return self._enable_darwin()
            else:
                return self._enable_linux()
        except Exception as exc:
            logger.error("Failed to enable autostart: %s", exc)
            return False

    def disable(self) -> bool:
        """Remove the autostart registration."""
        try:
            if self._system == "Windows":
                return self._disable_windows()
            elif self._system == "Darwin":
                return self._disable_darwin()
            else:
                return self._disable_linux()
        except Exception as exc:
            logger.error("Failed to disable autostart: %s", exc)
            return False

    def is_enabled(self) -> bool:
        try:
            if self._system == "Windows":
                return self._is_enabled_windows()
            elif self._system == "Darwin":
                return self._is_enabled_darwin()
            else:
                return self._is_enabled_linux()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _app_name(self) -> str:
        return "LaptopMomentum"

    def _pythonw_path(self) -> str | None:
        """Return the path to ``pythonw.exe`` on Windows, or None."""
        if self._system != "Windows":
            return None
        exe = sys.executable  # e.g. ...\python.exe
        w = exe.removesuffix("python.exe") + "pythonw.exe"
        return w if os.path.isfile(w) else None

    def _app_command(self) -> str:
        """Return the full command-line string to launch the app.

        * PyInstaller bundle: just the exe path.
        * Source (dev):      quoted interpreter (pythonw if available) + main.py.
        """
        if getattr(sys, "frozen", False):
            return sys.executable
        interpreter = self._pythonw_path() or sys.executable
        app_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(app_dir)
        main_py = os.path.join(project_root, "main.py")
        return f'"{interpreter}" "{main_py}"'

    def _app_command_array(self) -> list[str]:
        """Arguments array form for macOS LaunchAgent plists."""
        if getattr(sys, "frozen", False):
            return [sys.executable]
        interpreter = self._pythonw_path() or sys.executable
        app_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(app_dir)
        main_py = os.path.join(project_root, "main.py")
        return [interpreter, main_py]

    # ------------------------------------------------------------------
    # Windows  (registry)
    # ------------------------------------------------------------------
    def _enable_windows(self) -> bool:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, self._app_name(), 0, winreg.REG_SZ, self._app_command())
        winreg.CloseKey(key)
        return True

    def _disable_windows(self) -> bool:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, self._app_name())
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        return True

    def _is_enabled_windows(self) -> bool:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, self._app_name())
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False

    # ------------------------------------------------------------------
    # Desktop right-click context menu (Windows)
    # ------------------------------------------------------------------
    _DESKTOP_MENU_KEY = r"Software\Classes\DesktopBackground\Shell\LaptopMomentum"

    def enable_desktop_menu(self) -> bool:
        """Add the app to the desktop background right-click menu so the user
        can relaunch it easily if it ever crashes."""
        if self._system != "Windows":
            return False
        import winreg
        try:
            cmd = self._app_command()
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._DESKTOP_MENU_KEY)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Laptop Momentum")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, self._app_command().strip('"'))
            winreg.SetValueEx(key, "Position", 0, winreg.REG_SZ, "Bottom")
            winreg.CloseKey(key)

            cmd_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                       self._DESKTOP_MENU_KEY + r"\command")
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(cmd_key)
            return True
        except Exception as exc:
            logger.error("Failed to enable desktop menu: %s", exc)
            return False

    def disable_desktop_menu(self) -> bool:
        """Remove the desktop right-click menu entry."""
        if self._system != "Windows":
            return False
        import winreg
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                             self._DESKTOP_MENU_KEY + r"\command")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self._DESKTOP_MENU_KEY)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.error("Failed to disable desktop menu: %s", exc)
            return False
        return True

    def is_desktop_menu_enabled(self) -> bool:
        if self._system != "Windows":
            return False
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 self._DESKTOP_MENU_KEY, 0, winreg.KEY_READ)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False

    # ------------------------------------------------------------------
    # macOS  (LaunchAgent plist)
    # ------------------------------------------------------------------
    def _plist_path(self) -> str:
        name = f"com.{self._app_name().lower()}.plist"
        return os.path.expanduser(f"~/Library/LaunchAgents/{name}")

    def _enable_darwin(self) -> bool:
        path = self._plist_path()
        args = self._app_command_array()
        args_xml = "\n".join(f"        <string>{a}</string>" for a in args)
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self._app_name()}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
        with open(path, "w") as f:
            f.write(content)
        os.chmod(path, 0o644)
        return True

    def _disable_darwin(self) -> bool:
        path = self._plist_path()
        if os.path.exists(path):
            os.remove(path)
        return True

    def _is_enabled_darwin(self) -> bool:
        return os.path.exists(self._plist_path())

    # ------------------------------------------------------------------
    # Linux  (XDG autostart .desktop)
    # ------------------------------------------------------------------
    def _desktop_path(self) -> str:
        return os.path.expanduser(f"~/.config/autostart/{self._app_name().lower()}.desktop")

    def _enable_linux(self) -> bool:
        path = self._desktop_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = f"""[Desktop Entry]
Type=Application
Name={self._app_name()}
Exec={self._app_command()}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
        with open(path, "w") as f:
            f.write(content)
        return True

    def _disable_linux(self) -> bool:
        path = self._desktop_path()
        if os.path.exists(path):
            os.remove(path)
        return True

    def _is_enabled_linux(self) -> bool:
        return os.path.exists(self._desktop_path())
