import os
import sys
import platform
from pathlib import Path
from datetime import datetime, timedelta, date

# ---------------------------------------------------------------------------
# Load .env file (manual parser, no dependency required)
# ---------------------------------------------------------------------------
_ENV_CANDIDATES: list[Path] = []
if getattr(sys, "frozen", False):
    _ENV_CANDIDATES.append(Path(sys.executable).parent / ".env")
else:
    _ENV_CANDIDATES.append(Path(__file__).resolve().parent.parent / ".env")
_ENV_CANDIDATES.append(Path.cwd() / ".env")
_ENV_CANDIDATES.append(Path.cwd() / "dist" / ".env")
for _p in _ENV_CANDIDATES:
    if _p.is_file():
        try:
            for _line in _p.read_text(encoding="utf-8").splitlines():
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _key, _val = _line.split("=", 1)
                _key = _key.strip()
                _val = _val.strip().strip("\"'")
                if _key and _val:
                    os.environ.setdefault(_key, _val)
        except Exception:
            pass
        break

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

# Activity quality scoring (anti-automation).
QUALITY_WINDOW_SECONDS    = 60     # rolling analysis window
QUALITY_MIN_EVENTS        = 5      # minimum events before scoring activates
QUALITY_MIN_GAPS          = 3      # minimum inter-event gaps for timing check
QUALITY_GAP_MAX_SECONDS   = 2      # ignore gaps longer than this (idle separation)
QUALITY_MODIFIER_RATIO    = 0.03   # modifier / key-press ratio threshold

# Fraction of active seconds that count when quality is below threshold.
# score >= QUALITY_HIGH_THRESHOLD → 100 %
# score >= QUALITY_LOW_THRESHOLD  → QUALITY_MEDIUM_FRACTION
# score <  QUALITY_LOW_THRESHOLD  → 0 %
QUALITY_HIGH_THRESHOLD    = 0.5
QUALITY_LOW_THRESHOLD     = 0.2
QUALITY_MEDIUM_FRACTION   = 0.5

# Random bonus point chance (per active tick).
RANDOM_BONUS_CHANCE       = 0.33

# Mystery bonus on first activity after day boundary.
MYSTERY_BONUS_MIN         = 1
MYSTERY_BONUS_MAX         = 5
MYSTERY_BONUS_CUTOFF_HOUR = 12  # only trigger before noon

# Streak tiers — milestone labels shown on the dashboard.
STREAK_TIERS: dict[int, str] = {
    7:   "Consistent",
    30:  "Dedicated",
    100: "Unstoppable",
    365: "Legendary",
}

# Maximum streak freezes per week.
MAX_FREEZES_PER_WEEK      = 1

# Daily active target.
DAILY_TARGET_DEFAULT      = 30    # default daily target in minutes
DAILY_TARGET_MIN          = 10    # minimum (same as streak minimum)
DAILY_TARGET_MAX          = 240   # maximum (4 hours)

# Focus session: uninterrupted active block counts as a "focus session".
FOCUS_SESSION_MIN_SECONDS = 1200  # 20 minutes

# Vacation mode: pause streak by consuming lifelines.
VACATION_MAX_DAYS         = 3     # max vacation days at a time

# Lifeline debt: pre-use a lifeline you don't have yet.
LIFELINE_DEBT_LIMIT       = 2     # max lifelines you can owe

# Phone notification (ntfy.sh).
PHONE_NOTIFIER_ENABLED    = False
PHONE_NOTIFIER_HOUR       = 20    # 8 PM — start checking for phone alerts
PHONE_NOTIFIER_INTERVAL   = 30    # minutes between repeated phone alerts
NTFY_TOPIC                = os.environ.get("NTFY_TOPIC", "")  # alerts: phone subscribes here
NTFY_STATUS_TOPIC         = os.environ.get("NTFY_STATUS_TOPIC", "")  # heartbeats: GitHub Actions reads here

# Achievement definitions.
# Each entry: (key, label, description, check_fn_name)
ACHIEVEMENTS: list[dict] = [
    {"key": "first_streak",    "label": "First Step",      "desc": "Reach a 7-day streak"},
    {"key": "dedicated",       "label": "Dedicated",       "desc": "Reach a 30-day streak"},
    {"key": "unstoppable",     "label": "Unstoppable",     "desc": "Reach a 100-day streak"},
    {"key": "legendary",       "label": "Legendary",       "desc": "Reach a 365-day streak"},
    {"key": "early_bird",      "label": "Early Bird",      "desc": "Active before 8 AM for 7 days"},
    {"key": "night_owl",       "label": "Night Owl",       "desc": "Active after midnight for 7 days"},
    {"key": "iron_will",       "label": "Iron Will",       "desc": "30-day streak without using a freeze"},
    {"key": "marathoner",      "label": "Marathoner",      "desc": "Accumulate 100 hours of active time"},
    {"key": "centurion",       "label": "Centurion",       "desc": "Earn 1000 points in a single week"},
    {"key": "focus_master",    "label": "Focus Master",    "desc": "Complete 50 focus sessions"},
]

# Sound effect file names (bundled in the exe or generated at runtime).
SOUND_MILESTONE   = "milestone.wav"
SOUND_BONUS       = "bonus.wav"
SOUND_ACHIEVEMENT = "achievement.wav"


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
