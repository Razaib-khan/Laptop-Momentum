import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QGroupBox, QGridLayout, QFrame, QScrollArea,
)

from app import config


_STYLE = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "SF Pro Display", "Noto Sans", sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
    font-size: 12px;
    color: #a6adc8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLabel#valueLabel {
    font-size: 22px;
    font-weight: 700;
    color: #cdd6f4;
}
QLabel#unitLabel {
    font-size: 11px;
    color: #6c7086;
}
QLabel#timerLabel {
    font-size: 48px;
    font-weight: 700;
    color: #f5c2e7;
    font-variant-numeric: tabular-nums;
}
QLabel#nextPointLabel {
    font-size: 14px;
    color: #a6e3a1;
}
QListWidget {
    border: 1px solid #45475a;
    border-radius: 6px;
    background-color: #181825;
    padding: 4px;
    font-size: 11px;
}
QListWidget::item {
    padding: 2px 6px;
    border-bottom: 1px solid #313244;
}
"""


def _format_hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class StatCard(QFrame):
    """A small card that shows a label, a large value, and an optional unit."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            StatCard {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self.title_label = QLabel(title.upper())
        self.title_label.setStyleSheet("font-size: 10px; color: #6c7086; font-weight: 600; letter-spacing: 1px;")

        self.value_label = QLabel("--")
        self.value_label.setObjectName("valueLabel")

        self.unit_label = QLabel("")
        self.unit_label.setObjectName("unitLabel")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.unit_label)

    def set_value(self, value: str, unit: str = ""):
        self.value_label.setText(value)
        self.unit_label.setText(unit)


class Dashboard(QWidget):
    """Main stats window.  Refreshes every 5 s from the backend, plus a 1-second
    local timer that smoothly updates the HH:MM:SS and next-point display."""

    def __init__(self, get_state_cb):
        super().__init__()
        self._get_state = get_state_cb
        self.setWindowTitle("Laptop Momentum")
        self.setMinimumSize(520, 480)
        self.resize(560, 720)

        self.setStyleSheet(_STYLE)

        # Cached state for the 1-second timer projection.
        self._cached_state = {}

        # ---------- Scroll area ----------
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(12)

        # Header
        header = QLabel("Laptop Momentum")
        header.setStyleSheet("font-size: 20px; font-weight: 700; color: #f5c2e7; letter-spacing: 1px;")
        header.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(header)

        # Status line
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 12px; color: #a6adc8;")
        content_layout.addWidget(self.status_label)

        # ---------- Active Time (real-time timer) ----------
        timer_group = QGroupBox("Active Time Today")
        timer_layout = QVBoxLayout(timer_group)
        timer_layout.setAlignment(Qt.AlignCenter)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("timerLabel")
        self.timer_label.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.timer_label)

        self.next_point_label = QLabel("")
        self.next_point_label.setObjectName("nextPointLabel")
        self.next_point_label.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.next_point_label)

        content_layout.addWidget(timer_group)

        # ---------- Row 1: Streaks ----------
        streak_group = QGroupBox("Streak")
        streak_grid = QGridLayout(streak_group)
        streak_grid.setSpacing(12)

        self.card_current_streak = StatCard("Current")
        self.card_longest_streak = StatCard("Longest")
        streak_grid.addWidget(self.card_current_streak, 0, 0)
        streak_grid.addWidget(self.card_longest_streak, 0, 1)
        content_layout.addWidget(streak_group)

        # ---------- Row 2: Today ----------
        today_group = QGroupBox("Today")
        today_grid = QGridLayout(today_group)
        today_grid.setSpacing(12)

        self.card_today_minutes = StatCard("Active Minutes")
        self.card_today_points = StatCard("Points Earned")
        today_grid.addWidget(self.card_today_minutes, 0, 0)
        today_grid.addWidget(self.card_today_points, 0, 1)
        content_layout.addWidget(today_group)

        # ---------- Row 3: Records ----------
        record_group = QGroupBox("Records")
        record_grid = QGridLayout(record_group)
        record_grid.setSpacing(12)

        self.card_highest_uptime = StatCard("Highest Active Time")
        record_grid.addWidget(self.card_highest_uptime, 0, 0)
        content_layout.addWidget(record_group)

        # ---------- Row 4: Weekly ----------
        week_group = QGroupBox("Week")
        week_grid = QGridLayout(week_group)
        week_grid.setSpacing(12)

        self.card_weekly_points = StatCard("Points")
        self.card_weekly_target = StatCard("Target")
        self.card_lifelines = StatCard("Lifelines")
        week_grid.addWidget(self.card_weekly_points, 0, 0)
        week_grid.addWidget(self.card_weekly_target, 0, 1)
        week_grid.addWidget(self.card_lifelines, 0, 2)
        content_layout.addWidget(week_group)

        # ---------- Recent activity ----------
        log_label = QLabel("RECENT ACTIVITY")
        log_label.setStyleSheet("font-size: 10px; color: #6c7086; font-weight: 600; letter-spacing: 1px; "
                                "margin-top: 8px;")
        content_layout.addWidget(log_label)

        self.activity_list = QListWidget()
        self.activity_list.setMaximumHeight(160)
        content_layout.addWidget(self.activity_list)

        content_layout.addStretch()

        # ---------- Main window layout ----------
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(content)
        root.addWidget(scroll)

        # ---------- 5-second backend refresh timer ----------
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(config.DASHBOARD_REFRESH_MS)

        # ---------- 1-second UI projection timer ----------
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._update_timer_display)
        self._ui_timer.start(1000)

        self._last_refresh_time = 0.0

        # Initial load.
        self._refresh()

    # ------------------------------------------------------------------
    # Refresh (5-second, from the backend)
    # ------------------------------------------------------------------
    def _refresh(self):
        now = time.time()
        state = self._get_state()
        self._cached_state = state
        self._last_refresh_time = now

        self.card_current_streak.set_value(
            str(state["current_streak"]),
            "days" if state["current_streak"] != 1 else "day",
        )
        self.card_longest_streak.set_value(
            str(state["longest_streak"]),
            "days" if state["longest_streak"] != 1 else "day",
        )
        self.card_today_minutes.set_value(
            str(state["today_active_minutes"]),
        )
        self.card_today_points.set_value(
            str(state["today_points"]),
        )
        self.card_weekly_points.set_value(
            str(state["weekly_points"]),
            f"/ {state['weekly_target']} target",
        )
        self.card_weekly_target.set_value(
            str(state["weekly_target"]),
        )
        self.card_lifelines.set_value(
            str(state["lifelines"]),
        )

        # Highest uptime record
        highest_sec = state.get("highest_uptime_seconds", 0)
        highest_date = state.get("highest_uptime_date")
        if highest_sec > 0 and highest_date:
            h = highest_sec // 3600
            m = (highest_sec % 3600) // 60
            s = highest_sec % 60
            self.card_highest_uptime.set_value(
                f"{h:02d}:{m:02d}:{s:02d}",
                f"on {highest_date}",
            )
        else:
            self.card_highest_uptime.set_value("--")

        # Status
        if state.get("is_active", False):
            self.status_label.setText("Status: Active")
            self.status_label.setStyleSheet("font-size: 12px; color: #a6e3a1;")
        else:
            self.status_label.setText("Status: Paused (idle)")
            self.status_label.setStyleSheet("font-size: 12px; color: #f9e2af;")

        # Recent events
        self.activity_list.clear()
        events = state.get("recent_events", [])
        if not events:
            self.activity_list.addItem("No activity recorded yet.")
        else:
            for ev in events:
                text = f"{ev['timestamp']}  |  {ev['message']}"
                item = QListWidgetItem(text)
                self.activity_list.addItem(item)

        # Also update the timer display immediately.
        self._update_timer_display()

    def refresh(self):
        """Public alias called from the tray when state changes."""
        self._refresh()

    # ------------------------------------------------------------------
    # 1-second timer projection (smooth HH:MM:SS in the UI)
    # ------------------------------------------------------------------
    def _update_timer_display(self):
        state = self._cached_state
        if not state:
            return

        base_seconds = state.get("today_active_seconds", 0)
        is_active = state.get("is_active", False)

        # Project forward if the user is still active.
        if is_active and self._last_refresh_time > 0:
            elapsed = time.time() - self._last_refresh_time
            projected = base_seconds + int(elapsed)
        else:
            projected = base_seconds

        # Clamp to avoid negative.
        if projected < 0:
            projected = 0

        # HH:MM:SS display
        self.timer_label.setText(_format_hms(projected))

        # Next-point countdown
        threshold_sec = config.POINTS_THRESHOLD_MINUTES * 60
        if projected < threshold_sec:
            remaining = threshold_sec - projected
            self.next_point_label.setText(f"Points start in     {remaining // 60}:{remaining % 60:02d}")
            self.next_point_label.setStyleSheet("font-size: 14px; color: #f9e2af;")
        else:
            earned_extra = (projected - threshold_sec) // 60
            next_in = 60 - ((projected - threshold_sec) % 60)
            self.next_point_label.setText(
                f"Next point in    {next_in // 60}:{next_in % 60:02d}    "
                f"(+{earned_extra} today)")
            self.next_point_label.setStyleSheet("font-size: 14px; color: #a6e3a1;")

    def closeEvent(self, event):
        """Override close to just hide the window instead of destroying it."""
        self.hide()
        event.ignore()
