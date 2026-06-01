import time
from threading import Lock

import app.config as config


class ActivityScorer:
    """Estimates how "human" recent input activity looks.

    Returns a quality score (0.0 – 1.0) on each call to *get_quality()*.
    Metrics are computed from events in the last *QUALITY_WINDOW_SECONDS*
    so the score adapts as input patterns change.

    A looped automation script typically:
      * Uses only one input type (e.g. just mouse clicks)
      * Never presses modifier keys (Ctrl / Alt / Shift / Win)
      * Has unnaturally regular timing
    """

    def __init__(self):
        self._lock = Lock()
        # Each entry: (timestamp, kind, is_modifier)
        # kind: "key" | "modifier" | "move" | "click" | "scroll"
        self._events: list[tuple[float, str, bool]] = []
        self._last_event_time: float | None = None

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_key(self, is_modifier: bool = False):
        kind = "modifier" if is_modifier else "key"
        self._add_event(kind, is_modifier)

    def record_mouse_move(self):
        self._add_event("move", False)

    def record_mouse_click(self):
        self._add_event("click", False)

    def record_mouse_scroll(self):
        self._add_event("scroll", False)

    def _add_event(self, kind: str, is_modifier: bool):
        now = time.time()
        with self._lock:
            self._prune(now)
            self._events.append((now, kind, is_modifier))
            self._last_event_time = now

    def _prune(self, now: float | None = None):
        if now is None:
            now = time.time()
        cutoff = now - config.QUALITY_WINDOW_SECONDS
        # Remove events older than the window.
        self._events = [e for e in self._events if e[0] >= cutoff]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def get_quality(self) -> float:
        """Return 0.0 (confidently automated) – 1.0 (confidently human)."""
        now = time.time()
        with self._lock:
            self._prune(now)
            events = list(self._events)

        total_events = len(events)

        # Not enough data yet — give benefit of the doubt.
        if total_events < config.QUALITY_MIN_EVENTS:
            return 1.0

        # Derive counters from the windowed event list.
        key_count = 0
        mod_count = 0
        click_count = 0
        has_move = False
        type_set: set[str] = set()
        for _, kind, is_mod in events:
            if kind == "key":
                key_count += 1
                type_set.add("key")
            elif kind == "modifier":
                key_count += 1
                mod_count += 1
                type_set.add("key")
            elif kind == "move":
                has_move = True
                type_set.add("move")
            elif kind == "click":
                click_count += 1
                type_set.add("click")
            elif kind == "scroll":
                type_set.add("scroll")

        has_mouse = has_move or click_count > 0

        # Inter-event gaps from windowed events (all types).
        gaps: list[float] = []
        prev = None
        for ts, _, _ in events:
            if prev is not None:
                gap = ts - prev
                if gap < config.QUALITY_GAP_MAX_SECONDS:
                    gaps.append(gap)
            prev = ts

        score = 0.0

        # 1. Input diversity (0 – 0.35)
        has_keyboard = key_count > 0
        if has_keyboard and has_mouse:
            score += 0.35
        elif has_keyboard or has_mouse:
            score += 0.15

        # 2. Modifier‑key usage (0 – 0.25)
        if key_count > 0:
            mod_ratio = mod_count / key_count
            if mod_ratio >= config.QUALITY_MODIFIER_RATIO:
                score += 0.25
            elif mod_ratio > 0:
                score += 0.12

        # 3. Timing variance (0 – 0.25)
        if len(gaps) >= config.QUALITY_MIN_GAPS:
            mean = sum(gaps) / len(gaps)
            if mean > 0:
                deviations = [abs(g - mean) for g in gaps]
                avg_dev = sum(deviations) / len(deviations)
                relative_dev = avg_dev / mean
                if relative_dev > 0.3:
                    score += 0.25
                elif relative_dev > 0.1:
                    score += 0.12

        # 4. Mouse click diversity (0 – 0.15)
        if click_count > 0 and has_move:
            score += 0.15

        return min(1.0, max(0.0, score))

    def reset(self):
        with self._lock:
            self._events.clear()
            self._last_event_time = None
