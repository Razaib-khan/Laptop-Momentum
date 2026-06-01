import time
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QGroupBox, QGridLayout, QFrame, QScrollArea,
    QProgressBar,
)

import app.config as config


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
QLabel#heatmapCell {
    font-size: 8px;
    min-width: 20px;
    max-width: 20px;
    min-height: 14px;
    max-height: 14px;
    border: 1px solid #313244;
    border-radius: 2px;
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


def _format_hms(seconds: int | float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _heatmap_color(minutes: int, target: int) -> str:
    """Return a hex colour for the heatmap cell based on active minutes."""
    if minutes <= 0:
        return "#181825"
    if minutes < config.STREAK_MINIMUM_MINUTES:
        return "#313244"
    ratio = min(1.0, minutes / max(target, 1))
    if ratio >= 1.0:
        return "#a6e3a1"
    if ratio >= 0.7:
        return "#a6e3a1"
    if ratio >= 0.4:
        return "#585b70"
    return "#45475a"


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
        self.resize(560, 850)
        screen = QGuiApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.setGeometry(
                sg.x() + (sg.width() - 560) // 2,
                sg.y() + (sg.height() - 850) // 2,
                560, 850
            )

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

        # Activity quality indicator
        quality_row = QHBoxLayout()
        quality_row.setAlignment(Qt.AlignCenter)
        self.quality_dot = QLabel("●")
        self.quality_dot.setStyleSheet("font-size: 10px; color: #a6e3a1;")
        self.quality_label = QLabel("Quality: High")
        self.quality_label.setStyleSheet("font-size: 11px; color: #a6adc8;")
        quality_row.addWidget(self.quality_dot)
        quality_row.addWidget(self.quality_label)
        timer_layout.addLayout(quality_row)

        content_layout.addWidget(timer_group)

        # ---------- Row 1: Streaks ----------
        streak_group = QGroupBox("Streak")
        streak_grid = QGridLayout(streak_group)
        streak_grid.setSpacing(12)

        self.card_current_streak = StatCard("Current")
        self.card_longest_streak = StatCard("Longest")
        self.card_streak_tier = StatCard("Tier")
        streak_grid.addWidget(self.card_current_streak, 0, 0)
        streak_grid.addWidget(self.card_longest_streak, 0, 1)
        streak_grid.addWidget(self.card_streak_tier, 0, 2)
        content_layout.addWidget(streak_group)

        # ---------- Row 2: Today ----------
        today_group = QGroupBox("Today")
        today_grid = QGridLayout(today_group)
        today_grid.setSpacing(12)

        self.card_today_minutes = StatCard("Active Minutes")
        self.card_today_points = StatCard("Points Earned")
        self.card_daily_target = StatCard("Daily Target")
        self.card_focus = StatCard("Focus Sessions")
        today_grid.addWidget(self.card_today_minutes, 0, 0)
        today_grid.addWidget(self.card_today_points, 0, 1)
        today_grid.addWidget(self.card_daily_target, 1, 0)
        today_grid.addWidget(self.card_focus, 1, 1)
        content_layout.addWidget(today_group)

        # ---------- Row 3: Records ----------
        record_group = QGroupBox("Records")
        record_grid = QGridLayout(record_group)
        record_grid.setSpacing(12)

        self.card_highest_uptime = StatCard("Highest Active Time")
        self.card_total_hours = StatCard("Total Active Time")
        self.card_best_week = StatCard("Best Week")
        record_grid.addWidget(self.card_highest_uptime, 0, 0)
        record_grid.addWidget(self.card_total_hours, 0, 1)
        record_grid.addWidget(self.card_best_week, 1, 0)
        content_layout.addWidget(record_group)

        # ---------- Row 4: Weekly ----------
        week_group = QGroupBox("Week")
        week_grid = QGridLayout(week_group)
        week_grid.setSpacing(12)

        self.weekly_progress = QProgressBar()
        self.weekly_progress.setRange(0, 100)
        self.weekly_progress.setValue(0)
        self.weekly_progress.setTextVisible(True)
        self.weekly_progress.setFixedHeight(26)
        self.weekly_progress.setStyleSheet("""
            QProgressBar {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                text-align: center;
                font-size: 11px;
                color: #cdd6f4;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f5c2e7, stop:1 #a6e3a1);
                border-radius: 3px;
            }
        """)
        week_grid.addWidget(self.weekly_progress, 0, 0, 1, 2)

        self.card_weekly_target = StatCard("Target")
        self.card_lifelines = StatCard("Lifelines")
        week_grid.addWidget(self.card_weekly_target, 1, 0)
        week_grid.addWidget(self.card_lifelines, 1, 1)
        content_layout.addWidget(week_group)

        # ---------- Calendar heatmap ----------
        heat_group = QGroupBox("Activity (Last 7 Weeks)")
        heat_layout = QVBoxLayout(heat_group)
        heat_layout.setSpacing(0)

        self.heatmap_grid = QGridLayout()
        self.heatmap_grid.setSpacing(1)
        self.heatmap_grid.setContentsMargins(0, 0, 0, 0)

        # Column headers (Mon–Sun) in row 0
        for j, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            lbl = QLabel(day_name)
            lbl.setStyleSheet("font-size: 7px; color: #6c7086;")
            lbl.setAlignment(Qt.AlignCenter)
            self.heatmap_grid.addWidget(lbl, 0, j + 1)

        self.heatmap_cells: list[QLabel] = []
        for i in range(7):  # weeks
            for j in range(7):  # days of week
                cell = QLabel()
                cell.setObjectName("heatmapCell")
                cell.setAlignment(Qt.AlignCenter)
                cell.setStyleSheet("background-color: #181825; border: 1px solid #313244; border-radius: 2px; font-size: 7px; color: #6c7086;")
                self.heatmap_grid.addWidget(cell, j + 1, i + 1)  # row 1-7, col 1-7
                self.heatmap_cells.append(cell)
        heat_layout.addLayout(self.heatmap_grid)
        content_layout.addWidget(heat_group)

        # ---------- Achievements ----------
        ach_group = QGroupBox("Achievements")
        ach_layout = QVBoxLayout(ach_group)
        self.ach_widgets: list[QLabel] = []
        for ach in config.ACHIEVEMENTS:
            row = QHBoxLayout()
            dot = QLabel("○")
            dot.setStyleSheet("font-size: 14px; color: #6c7086; min-width: 18px;")
            label = QLabel(f"{ach['label']} — {ach['desc']}")
            label.setStyleSheet("font-size: 11px; color: #6c7086;")
            row.addWidget(dot)
            row.addWidget(label)
            row.addStretch()
            ach_layout.addLayout(row)
            self.ach_widgets.append((dot, label, ach["key"]))
        content_layout.addWidget(ach_group)

        # ---------- Recent activity ----------
        log_label = QLabel("RECENT ACTIVITY")
        log_label.setStyleSheet("font-size: 10px; color: #6c7086; font-weight: 600; letter-spacing: 1px; "
                                "margin-top: 8px;")
        content_layout.addWidget(log_label)

        self.activity_list = QListWidget()
        self.activity_list.setMaximumHeight(140)
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

        # -- Streak --
        self.card_current_streak.set_value(
            str(state["current_streak"]),
            "days" if state["current_streak"] != 1 else "day",
        )
        self.card_longest_streak.set_value(
            str(state["longest_streak"]),
            "days" if state["longest_streak"] != 1 else "day",
        )
        longest = state["longest_streak"]
        tier_name = "--"
        for threshold, name in sorted(config.STREAK_TIERS.items()):
            if longest >= threshold:
                tier_name = name
        self.card_streak_tier.set_value(tier_name)

        # -- Today --
        today_min = state["today_active_minutes"]
        self.card_today_minutes.set_value(str(today_min))

        self.card_today_points.set_value(str(state["today_points"]))

        daily_target = state.get("daily_target", config.DAILY_TARGET_DEFAULT)
        target_progress = f"{today_min} / {daily_target} min"
        if today_min >= daily_target:
            target_progress += "  ✓"
        self.card_daily_target.set_value(target_progress)

        focus_today = state.get("focus_sessions_today", 0)
        focus_total = state.get("total_focus_sessions", 0)
        self.card_focus.set_value(str(focus_today), f"{focus_total} lifetime")

        # -- Weekly --
        weekly_pts = state["weekly_points"]
        target = state["weekly_target"]
        pct = min(100, int(weekly_pts / target * 100)) if target > 0 else 0
        self.weekly_progress.setRange(0, target)
        self.weekly_progress.setValue(min(weekly_pts, target))
        self.weekly_progress.setFormat(f"{weekly_pts} / {target}  ({pct}%)")

        self.card_weekly_target.set_value(str(state["weekly_target"]))

        lifeline_text = str(state["lifelines"])
        debt = state.get("lifeline_debt", 0)
        if debt > 0:
            lifeline_text += f" ({debt} owed)"
        last_week = state.get("last_week_points", 0)
        if last_week > 0:
            if weekly_pts > last_week:
                lifeline_text += "  ▲"
            elif weekly_pts < last_week:
                lifeline_text += "  ▼"
            else:
                lifeline_text += "  →"
        self.card_lifelines.set_value(lifeline_text)

        # -- Records --
        highest_sec = state.get("highest_uptime_seconds", 0)
        highest_date = state.get("highest_uptime_date")
        if highest_sec > 0 and highest_date:
            h = highest_sec // 3600
            m = (highest_sec % 3600) // 60
            s = highest_sec % 60
            self.card_highest_uptime.set_value(f"{h:02d}:{m:02d}:{s:02d}", f"on {highest_date}")
        else:
            self.card_highest_uptime.set_value("--")

        total_sec = state.get("total_active_seconds", 0)
        th = total_sec // 3600
        tm = (total_sec % 3600) // 60
        self.card_total_hours.set_value(f"{th}h {tm}m", "lifetime")

        bests = state.get("personal_bests", {})
        best_week = bests.get("best_week")
        if best_week and best_week["points"] > 0:
            self.card_best_week.set_value(f"{best_week['points']} pts", f"starting {best_week['start']}")
        else:
            self.card_best_week.set_value("--")

        # -- Quality indicator --
        tier = state.get("quality_tier", "high")
        if tier == "high":
            dot_color = "#a6e3a1"
            label = "High"
        elif tier == "medium":
            dot_color = "#f9e2af"
            label = "Medium"
        else:
            dot_color = "#f38ba8"
            label = "Low"
        self.quality_dot.setStyleSheet(f"font-size: 10px; color: {dot_color};")
        self.quality_label.setText(f"Quality: {label}")

        # -- Vacation mode --
        vacation = state.get("vacation_mode", False)
        vdays = state.get("vacation_days_used", 0)
        if vacation:
            self.status_label.setText(
                f"Status: Active (Vacation mode — {vdays}/{config.VACATION_MAX_DAYS} days used)"
            )
            self.status_label.setStyleSheet("font-size: 12px; color: #89b4fa;")
        elif state.get("is_active", False):
            self.status_label.setText("Status: Active")
            self.status_label.setStyleSheet("font-size: 12px; color: #a6e3a1;")
        else:
            self.status_label.setText("Status: Paused (idle)")
            self.status_label.setStyleSheet("font-size: 12px; color: #f9e2af;")

        # -- Heatmap --
        heatmap = state.get("heatmap", [])
        if heatmap:
            for idx, cell in enumerate(self.heatmap_cells):
                if idx < len(heatmap):
                    d = heatmap[idx]
                    color = _heatmap_color(d["minutes"], daily_target)
                    cell.setStyleSheet(
                        f"background-color: {color}; border: 1px solid #313244; border-radius: 2px; "
                        f"font-size: 7px; color: #6c7086;"
                    )
                    cell.setToolTip(f"{d['date']}: {d['minutes']} min")
                else:
                    cell.setStyleSheet(
                        "background-color: #181825; border: 1px solid #313244; border-radius: 2px;"
                    )

        # -- Achievements --
        unlocked = set(state.get("achievements", []))
        for dot, label, key in self.ach_widgets:
            if key in unlocked:
                dot.setStyleSheet("font-size: 14px; color: #f5c2e7; min-width: 18px;")
                dot.setText("●")
                label.setStyleSheet("font-size: 11px; color: #cdd6f4;")
            else:
                dot.setStyleSheet("font-size: 14px; color: #6c7086; min-width: 18px;")
                dot.setText("○")
                label.setStyleSheet("font-size: 11px; color: #6c7086;")

        # -- Recent events --
        self.activity_list.clear()
        events = state.get("recent_events", [])
        if not events:
            self.activity_list.addItem("No activity recorded yet.")
        else:
            for ev in events:
                text = f"{ev['timestamp']}  |  {ev['message']}"
                item = QListWidgetItem(text)
                self.activity_list.addItem(item)

        self._update_timer_display()

    def refresh(self):
        self._refresh()

    # ------------------------------------------------------------------
    # 1-second timer projection (smooth HH:MM:SS in the UI)
    # ------------------------------------------------------------------
    def _update_timer_display(self):
        state = self._cached_state
        if not state:
            return

        base_seconds = state.get("effective_active_seconds", 0)
        is_active = state.get("is_active", False)

        if is_active and self._last_refresh_time > 0:
            elapsed = time.time() - self._last_refresh_time
            projected = base_seconds + int(elapsed)
        else:
            projected = base_seconds

        if projected < 0:
            projected = 0

        self.timer_label.setText(_format_hms(projected))

        threshold_sec = config.POINTS_THRESHOLD_MINUTES * 60
        if projected < threshold_sec:
            remaining = int(threshold_sec - projected)
            self.next_point_label.setText(f"Points start in     {remaining // 60}:{remaining % 60:02d}")
            self.next_point_label.setStyleSheet("font-size: 14px; color: #f9e2af;")
        else:
            earned_extra = int(projected - threshold_sec) // 60
            next_in = 60 - (int(projected - threshold_sec) % 60)
            self.next_point_label.setText(
                f"Next point in    {next_in // 60}:{next_in % 60:02d}    "
                f"(+{earned_extra} today)")
            self.next_point_label.setStyleSheet("font-size: 14px; color: #a6e3a1;")

    def closeEvent(self, event):
        self.hide()
        event.ignore()
