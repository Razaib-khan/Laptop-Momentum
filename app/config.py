import os
import sys
import platform
from datetime import datetime, timedelta, date

# Day boundary hour (4 AM by default).  Configurable via settings table.
DAY_BOUNDARY_HOUR = 4

# How many seconds of no input before considering the user idle.
IDLE_TIMEOUT_SECONDS = 60

# How often the activity monitor ticks (seconds).
TICK_INTERVAL_SECONDS = 10

# Minimum active minutes required for a day to count toward the streak.
STREAK_MINIMUM_MINUTES = 2

# Active minutes per day before points start accruing.
POINTS_THRESHOLD_MINUTES = 10

# Points per active minute above the threshold.
POINTS_PER_EXTRA_MINUTE = 1

# Maximum lifelines a user can hold.
MAX_LIFELINES = 3

# Weekly target default.
DEFAULT_WEEKLY_TARGET = 500

# Hour after which a "streak at risk" notification may fire.
STREAK_RISK_NOTIFICATION_HOUR = 21

# Notification duration (milliseconds).
NOTIFICATION_DURATION_MS = 5000

# How often the dashboard auto-refreshes (milliseconds).
DASHBOARD_REFRESH_MS = 5000

# Session bonus (uninterrupted activity perk).
# After *BONUS_SESSION_MIN_SECONDS* of consecutive active time, every
# *BONUS_INTERVAL_SECONDS* of continued activity earns 1 extra point.
BONUS_SESSION_MIN_SECONDS = 1800   # 30 minutes
BONUS_INTERVAL_SECONDS   = 120     # 2 minutes at a time


def get_data_dir() -> str:
    app_name = "LaptopMomentum"
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, app_name)
    elif system == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", app_name)
    else:
        xdg = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
        return os.path.join(xdg, app_name)


def get_day_key(dt: datetime | None = None) -> str:
    """Return 'YYYY-MM-DD' for the day bucket, shifted by DAY_BOUNDARY_HOUR.

    If the current local time is before 04:00, the date is rolled back by one
    day so that late-night activity belongs to the *previous* calendar day's
    bucket.
    """
    if dt is None:
        dt = datetime.now()
    if dt.hour < DAY_BOUNDARY_HOUR:
        dt = dt - timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def get_week_key(dt: datetime | None = None) -> str:
    """Return 'YYYY-MM-DD' of the Monday that starts the current week.

    Uses the 04:00-shifted date, then walks back to Monday.
    """
    if dt is None:
        dt = datetime.now()
    day_key = get_day_key(dt)
    d = date.fromisoformat(day_key)
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def date_from_key(key: str) -> date:
    return date.fromisoformat(key)


def add_days(key: str, n: int) -> str:
    d = date.fromisoformat(key)
    return (d + timedelta(days=n)).isoformat()
