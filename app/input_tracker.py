import time
import logging
from threading import Lock

try:
    from pynput import mouse, keyboard
except ImportError:
    mouse = None
    keyboard = None

from app.activity_scorer import ActivityScorer

logger = logging.getLogger(__name__)

_MODIFIER_KEYS = {
    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
    keyboard.Key.alt_gr,
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
} if keyboard is not None else set()


class InputTracker:
    """Listens for global keyboard and mouse events and records the last
    activity timestamp.

    Also feeds a quality scorer so the app can discount automated / scripted
    input and only reward genuine human activity.

    Both listeners run as daemon threads so they are automatically cleaned up
    when the main process exits.
    """

    def __init__(self, idle_timeout: float = 60.0):
        self._idle_timeout = idle_timeout
        self._last_activity = time.time()
        self._lock = Lock()
        self._mouse_listener = None
        self._keyboard_listener = None
        self._running = False

        # Quality scorer.
        self.scorer = ActivityScorer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self):
        if self._running:
            return
        self._running = True
        self._last_activity = time.time()
        self.scorer.reset()

        if mouse is not None and keyboard is not None:
            try:
                self._mouse_listener = mouse.Listener(on_move=self._on_move,
                                                       on_click=self._on_click,
                                                       on_scroll=self._on_scroll)
                self._keyboard_listener = keyboard.Listener(on_press=self._on_press,
                                                             on_release=self._on_release)
                self._mouse_listener.daemon = True
                self._keyboard_listener.daemon = True
                self._mouse_listener.start()
                self._keyboard_listener.start()
                logger.info("Input listeners started")
            except Exception as exc:
                logger.warning("Failed to start pynput listeners: %s", exc)
        else:
            logger.warning("pynput not available — input tracking disabled")

    def stop(self):
        self._running = False
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._keyboard_listener is not None:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
        logger.info("Input listeners stopped")

    def is_active(self, now: float | None = None) -> bool:
        """Return True if the user has generated an input event within the
        idle timeout window."""
        if now is None:
            now = time.time()
        with self._lock:
            return (now - self._last_activity) < self._idle_timeout

    @property
    def last_activity_time(self) -> float:
        with self._lock:
            return self._last_activity

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _touched(self):
        with self._lock:
            self._last_activity = time.time()

    def _on_move(self, x, y):
        self._touched()
        self.scorer.record_mouse_move()

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self._touched()
            self.scorer.record_mouse_click()

    def _on_scroll(self, x, y, dx, dy):
        self._touched()
        self.scorer.record_mouse_scroll()

    def _on_press(self, key):
        self._touched()
        is_mod = key in _MODIFIER_KEYS if hasattr(key, '__hash__') else False
        self.scorer.record_key(is_modifier=is_mod)

    def _on_release(self, key):
        self._touched()
