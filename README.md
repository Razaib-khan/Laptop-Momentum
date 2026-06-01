<div align="center">
  <img src="favicon.png" alt="Laptop Momentum" width="96" height="96">
  <h1 align="center">Laptop Momentum v2.0</h1>
  <p align="center">
    A local-first background app that tracks daily laptop keyboard &amp; mouse activity<br>
    to build streaks, earn points, and keep you consistent — no accounts, no cloud.
  </p>
</div>

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
  - [Core Rules](#core-rules)
  - [Point Calculation](#point-calculation)
  - [Activity Quality Scoring](#activity-quality-scoring)
  - [Session Bonus](#session-bonus)
  - [Mystery &amp; Random Bonuses](#mystery--random-bonuses)
  - [Lifelines &amp; Debt](#lifelines--debt)
  - [Streak Freeze &amp; Vacation Mode](#streak-freeze--vacation-mode)
  - [Focus Sessions](#focus-sessions)
  - [Daily Target](#daily-target)
  - [Achievements](#achievements)
  - [Phone Notifications (ntfy.sh)](#phone-notifications-ntfysh)
  - [Calendar Heatmap](#calendar-heatmap)
  - [Weekly Target (Auto)](#weekly-target-auto)
- [Architecture](#architecture)
- [For Users: Running on Any PC](#for-users-running-on-any-pc)
  - [Option A — Download the Pre-Built EXE (Recommended)](#option-a--download-the-pre-built-exe-recommended)
  - [Option B — Run from Source](#option-b--run-from-source)
  - [Option C — Build Your Own EXE](#option-c--build-your-own-exe)
- [For AI Coders / Contributors](#for-ai-coders--contributors)
  - [Regenerating Git-Ignored Files](#regenerating-git-ignored-files)
  - [Development Workflow](#development-workflow)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Tech Stack](#tech-stack)
- [License](#license)

---

## Features

- **Real activity tracking** — keyboard and mouse input (pynput hooks), not just screen-on time
- **Streak system** — consecutive days with ≥2 active minutes build your streak
- **Point system** — every minute beyond the first 10 earns 1 point
- **Session bonus** — after 30 uninterrupted minutes, every 2 minutes earns 3 points instead of 2
- **Activity quality scoring** — detects scripted/automated input and discounts credit accordingly
- **Mystery bonus** — 1–5 random bonus points on your first activity before noon
- **Random bonus** — 33 % chance per active tick for 1 extra point
- **Lifelines** — earned by exceeding your weekly target, used to save a broken streak
- **Lifeline debt** — pre-use up to 2 lifelines you don't have yet; repaid from future earnings
- **Streak freeze** — once per week, mark a day as frozen so it neither advances nor breaks the streak
- **Vacation mode** — up to 3 consecutive days off, each consuming one lifeline
- **Focus sessions** — 20-minute uninterrupted activity blocks tracked as a session
- **10 achievements** — passive badges for streaks, hours, focus sessions, early-bird/night-owl activity, and more
- **Calendar heatmap** — 7-week grid color-coded by daily active minutes
- **Auto weekly target** — adapts to your performance (no manual fiddling)
- **Daily active target** — adjustable goal (10–240 min) with a progress bar on the dashboard
- **Sound effects** — synthesized chimes for milestones, bonuses, and achievements
- **Phone push notifications** — optional ntfy.sh integration sends alerts when your streak is at risk
- **GitHub Actions backup** — scheduled workflow checks streak status even when the laptop is off
- **System tray** — runs silently in the background, right-click for all controls
- **Dashboard** — real-time timer (HH:MM:SS), streaks, points, weekly bar, heatmap, achievements, activity log
- **Desktop notifications** — streak-safe, now-earning-points, session-bonus, weekly-summary, and more
- **Windows startup on login** — optional, toggled from the tray menu
- **CSV export** — export daily stats to CSV from the tray menu
- **4 AM day boundary** — late-night owls keep yesterday's streak alive
- **Fully local** — SQLite database, no accounts, no telemetry

---

## How It Works

### Core Rules

| Concept | Detail |
|---|---|
| **Day** | Runs from **04:00** to the next day **03:59**. Activity before 4 AM counts toward the *previous* day. |
| **Week** | Runs from **Monday 04:00** to the next Monday **03:59**. |
| **Streak** | Every day with **≥2 effective active minutes** extends your streak by 1. Days below 2 minutes break it (unless saved by a lifeline or freeze). |
| **Effective vs. raw time** | Raw seconds are the total physical time with activity. Effective seconds apply the quality-scoring discount (100 % / 50 % / 0 % credit). Points and streaks use **effective** seconds. |
| **Points** | **0 points** for the first 10 effective minutes each day. **1 point per minute** after that. |
| **Session Bonus** | After **30 uninterrupted effective minutes**, every **2 minutes = 3 points** (instead of 2). Bonus resets when you go idle for ≥60 seconds. |
| **Lifelines** | **1 lifeline** per 10 points *over* the weekly target at the week boundary. Max 3 saved, up to 2 in debt. Automatically saves a missed streak day (before freezes). |
| **Weekly Target** | Calculated **automatically** each Monday based on your last 4 weeks, streak, momentum, and a weak-week reduction. |
| **Daily Target** | Adjustable per-day goal (default 30 minutes, range 10–240). Shown on the dashboard as a progress bar. |

### Point Calculation

```
raw_base = max(0, raw_effective_minutes - 10)
session_bonus = (uninterrupted_effective_seconds_beyond_1800 // 120) * 1
mystery_bonus = 1–5 (once per day, random, only before noon)
random_bonus  = 1 (33 % chance per active tick)
total_points_today = raw_base + session_bonus + mystery_bonus + random_bonus
```

**Example:** 45 effective minutes, 25 of which were part of a 35-minute uninterrupted session, with mystery bonus of 3:

- Base: `45 - 10 = 35 points`
- Session bonus: 5 minutes beyond 30-min threshold → `(300 // 120) = 2 bonus points`
- Mystery bonus: 3 points
- Random bonus: ~3 points (from ~12 active ticks × 33 %)
- Total: **43 points**

### Activity Quality Scoring

The app analyses keyboard/mouse event patterns in a rolling 60-second window to detect automation:

| Check | Weight | What it measures |
|---|---|---|
| Input diversity | 0.35 | Both keyboard *and* mouse present vs. only one |
| Modifier-key ratio | 0.25 | Enough Ctrl / Alt / Shift / Win presses (scripts rarely use them) |
| Timing variance | 0.25 | Inter-event gaps are irregular (humans) vs. uniform (scripts) |
| Mouse click diversity | 0.15 | Clicks *with* mouse movement vs. clicks without |

**Result:**
- **Green** (score ≥ 0.5) → full 100 % credit toward streak and points
- **Yellow** (score ≥ 0.2) → 50 % credit
- **Red** (score < 0.2) → 0 % credit (that tick is wasted)

The quality dot on the dashboard shows the current tier.

### Session Bonus

If you stay active (no 60-second idle gap) for ≥30 effective minutes:

- A notification fires: **"Session Bonus Active"**
- Every subsequent 2 minutes of continued activity awards **1 bonus point** (3 points per 2 minutes instead of 2)
- Going idle for 60 seconds resets the session counter; you need another 30 uninterrupted minutes to re-trigger

### Mystery &amp; Random Bonuses

- **Mystery bonus:** On the first activity tick after the 4 AM day boundary, *if it's before noon*, you earn a random 1–5 points. Only once per day.
- **Random bonus:** Every active tick has a 33 % chance to award 1 extra point. Rolled independently each tick.

### Lifelines &amp; Debt

- **Earning:** At each Monday boundary, every 10 points *above* the weekly target = 1 lifeline (max 3 held).
- **Consumption:** If a day ends with <2 effective minutes AND you have an active streak, a lifeline is consumed automatically to protect the streak.
- **Debt:** You can pre-use a lifeline (down to -2). Debt is repaid from future lifeline earnings before new lifelines accumulate. Shown on the dashboard as e.g. "Lifelines: 1 (-1 debt)".

### Streak Freeze &amp; Vacation Mode

Both are toggled from the tray menu.

- **Streak freeze:** Once per calendar week, mark a day as frozen. That day counts as neither advancing nor breaking the streak. The steak continues as if the day never existed. Consumed *before* a lifeline.
- **Vacation mode:** Up to 3 consecutive days. Each missed day consumes one lifeline (or goes into debt). The dashboard shows "Vacation mode (X/3 days used)". Toggle off to resume normal tracking.

### Focus Sessions

An uninterrupted active block of **≥20 minutes** counts as one focus session. The dashboard shows today's count and a lifetime total. Used for the "Focus Master" achievement (50 sessions).

### Achievements

| Achievement | Requirement |
|---|---|
| **First Step** | Reach a 7-day streak |
| **Dedicated** | Reach a 30-day streak |
| **Unstoppable** | Reach a 100-day streak |
| **Legendary** | Reach a 365-day streak |
| **Early Bird** | Active before 8 AM for 7 days |
| **Night Owl** | Active after midnight for 7 days |
| **Iron Will** | 30-day streak without using a freeze |
| **Marathoner** | Accumulate 100 hours of active time |
| **Centurion** | Earn 1000 points in a single week |
| **Focus Master** | Complete 50 focus sessions |

Unlocked achievements are displayed on the dashboard with visual distinction.

### Phone Notifications (ntfy.sh)

Free push notifications for when your streak is at risk, using [ntfy.sh](https://ntfy.sh) — no registration, no API key.

**How it works:**

1. Set `NTFY_TOPIC` (a simple name like `Laptop_Momentum`) in `.env` or as an environment variable.
2. Install the [ntfy app](https://docs.ntfy.sh) on your Android phone and subscribe to that topic.
3. Enable **Phone Reminder** from the tray menu.
4. Starting at 8 PM (configurable), the app checks if you've hit the 2-minute streak minimum. If not, it sends a push notification. Repeats every 30 minutes if still at risk.
5. **Backup check via GitHub Actions (optional):** Even if the laptop is off at 8 PM, a scheduled GitHub Actions workflow fetches the latest heartbeat from a separate status topic and sends an alert to your phone. Set `NTFY_STATUS_TOPIC` in `.env` and add both as repository secrets on GitHub.

### Calendar Heatmap

The dashboard shows a 7-column × 7-row grid (49 days) representing the last 7 weeks. Each cell is coloured:

- **Dark / empty** — no activity on that day
- **Gray** — below the streak minimum (0 < minutes < 2)
- **Green** — target met or exceeded

Hover over a cell to see the exact date and active minutes.

### Weekly Target (Auto)

Recalculated every Monday 04:00 using:

```
base            = average points of last 4 weeks (or 500 if no history)
streak_bonus    = min(current_streak × 5, +50)
momentum_bonus  = (last_week_points - last_target) × 0.1   (only if positive)
weak_reduction  = -(last_target × 0.1)                      (only if last week < 50 % of target)
target          = clamp(base + streak_bonus + momentum_bonus - weak_reduction, 100, 2000)
```

---

## Architecture

```
laptop-momentum/
├── main.py                     # Entry point, console hiding, startup wiring
├── pyproject.toml              # Dependencies (PySide6, pynput, PyInstaller)
├── favicon.ico / favicon.png   # Application icons
├── .env                        # Secrets (NTFY_TOPIC, etc.) — gitignored
├── .env.example                # Template for .env — safe to commit
├── .gitattributes              # Line-ending normalisation
├── build/
│   └── laptop-momentum.spec    # PyInstaller spec (builds the EXE)
├── .github/
│   └── workflows/
│       └── check-streak.yml    # Scheduled streak-backup check via ntfy.sh
├── app/
│   ├── __init__.py
│   ├── config.py               # All constants, .env loader, day/week helpers
│   ├── database.py             # Thread-safe SQLite wrapper
│   ├── input_tracker.py        # pynput-based keyboard/mouse listener
│   ├── activity_monitor.py     # Central coordinator (10 s tick loop)
│   ├── activity_scorer.py      # Anti-automation quality scoring
│   ├── points_manager.py       # Points, session bonus, mystery/random bonuses
│   ├── streak_manager.py       # Streak state machine
│   ├── lifeline_manager.py     # Lifeline earn/consume/debt logic
│   ├── notification_manager.py # Desktop & milestone notifications
│   ├── phone_notifier.py       # ntfy.sh push notification & heartbeat sender
│   ├── sound_manager.py        # Synthesised WAV chimes via Qt Multimedia
│   ├── autostart_manager.py    # Windows registry startup toggle
│   └── ui/
│       ├── dashboard.py        # Scrollable stats window (timer, heatmap, achievements)
│       └── tray.py             # System tray icon, context menu, game rules
```

### Data Flow

```
InputTracker (pynput hooks)
    ↓  is_active() every 10 s
ActivityMonitor._on_tick()
    ├─ ActivityScorer (quality check on event window)
    ├─ PointsManager (base points, session bonus, mystery/random)
    ├─ StreakManager (advance / freeze / vacation)
    ├─ LifelineManager (debt, earn, consume)
    ├─ PhoneNotifier (heartbeats, risk alerts)
    └─ NotificationManager / SoundManager (alerts)
    ↓  checkpoint every 60 s
Database (SQLite, `{data_dir}/momentum.db`)
    ↓  state_updated Signal
TrayIcon (tooltip)  &  Dashboard (stats window, 5 s refresh)
```

---

## For Users: Running on Any PC

### Option A — Download the Pre-Built EXE (Recommended)

1. Grab `LaptopMomentum.exe` from the latest [Releases](https://github.com/YOUR_USER/YOUR_REPO/releases) page.
2. Place it anywhere you like (e.g. `C:\Program Files\LaptopMomentum\`).
3. (Optional) Create a `.env` file next to the EXE with your ntfy topic (see `.env.example`).
4. Double-click `LaptopMomentum.exe`. It runs silently in the system tray (bottom-right taskbar).

> **Tip:** Right-click the tray icon → **Run at Login** to have it start automatically when you log in.

### Option B — Run from Source

Requires **Python 3.14+** and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
# Clone the repo
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd laptop-momentum

# Create a virtual environment and install dependencies
uv sync

# Run in development mode
uv run python main.py
```

If you don't have `uv`, you can use `pip`:

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate  # macOS/Linux
pip install -e .
python main.py
```

> **Note for Linux:** pynput may require `sudo apt install python3-xlib` or platform-specific input permissions.
>
> **Note for macOS:** You may need to grant Accessibility permissions to Terminal/python under **System Settings → Privacy & Security → Accessibility**.

### Option C — Build Your Own EXE

After running `uv sync`:

```bash
# Using uv (recommended)
uv run pyinstaller build/laptop-momentum.spec

# Using pip
pyinstaller build/laptop-momentum.spec
```

The EXE appears at `dist\LaptopMomentum.exe`. You can copy it anywhere.

---

## For AI Coders / Contributors

### Regenerating Git-Ignored Files

The following directories/files are in `.gitignore` and **must be regenerated locally** after cloning:

| Ignored Path | How to Regenerate | Command |
|---|---|---|
| `.venv/` | Create virtual environment & install deps | `uv sync` |
| `build/*` (most files) | PyInstaller intermediate files | `uv run pyinstaller build/laptop-momentum.spec` |
| `dist/` | Standalone executable | `uv run pyinstaller build/laptop-momentum.spec` |
| `__pycache__/` | Auto-generated by Python | Auto (recreated on import) |
| `*.egg-info/` | Pip install metadata | `uv sync` or `pip install -e .` |
| `favicon_test.png` | Manual favicon test (not needed) | N/A |

**Quick-start command for an AI coder who just cloned the repo:**

```bash
# 1. Install Python 3.14+ (if not already)
# 2. Install uv
pip install uv

# 3. Create venv & install everything
uv sync

# 4. (Optional) Build the EXE
uv run pyinstaller build/laptop-momentum.spec

# 5. Run in development mode
uv run python main.py
```

### Development Workflow

1. Activate the virtual environment: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (macOS/Linux).
2. Make changes to the Python files under `app/` and `main.py`.
3. Test by running `uv run python main.py`.
4. To test the standalone EXE: `uv run pyinstaller build/laptop-momentum.spec && dist\LaptopMomentum.exe`.
5. The database and logs are at `%APPDATA%\LaptopMomentum\` (Windows) or `~/Library/Application Support/LaptopMomentum/` (macOS) or `~/.local/share/LaptopMomentum/` (Linux).

---

## Configuration

All tunable constants live in `app/config.py`:

### Core

| Constant | Default | Description |
|---|---|---|
| `DAY_BOUNDARY_HOUR` | `4` | Hour (24 h) when a new day starts |
| `IDLE_TIMEOUT_SECONDS` | `60` | Seconds of no input before considered idle |
| `TICK_INTERVAL_SECONDS` | `10` | Activity monitor loop interval |
| `STREAK_MINIMUM_MINUTES` | `2` | Minimum effective active minutes for a streak day |
| `POINTS_THRESHOLD_MINUTES` | `10` | Effective minutes before points start accruing |
| `POINTS_PER_EXTRA_MINUTE` | `1` | Points per effective minute above the threshold |
| `MAX_LIFELINES` | `3` | Maximum lifelines a user can hold |
| `LIFELINE_DEBT_LIMIT` | `2` | Maximum lifelines a user can owe |
| `DEFAULT_WEEKLY_TARGET` | `500` | Fallback weekly target when no history |

### Session Bonus

| Constant | Default | Description |
|---|---|---|
| `BONUS_SESSION_MIN_SECONDS` | `1800` | Seconds of consecutive activity to trigger bonus |
| `BONUS_INTERVAL_SECONDS` | `120` | Bonus award interval (seconds) |

### Activity Quality Scoring

| Constant | Default | Description |
|---|---|---|
| `QUALITY_WINDOW_SECONDS` | `60` | Rolling event-analysis window |
| `QUALITY_MIN_EVENTS` | `5` | Minimum events before scoring activates |
| `QUALITY_MIN_GAPS` | `3` | Minimum inter-event gaps for timing check |
| `QUALITY_GAP_MAX_SECONDS` | `2` | Ignore gaps longer than this (idle separation) |
| `QUALITY_MODIFIER_RATIO` | `0.03` | Modifier / key-press ratio threshold |
| `QUALITY_HIGH_THRESHOLD` | `0.5` | Score ≥ this → 100 % credit |
| `QUALITY_LOW_THRESHOLD` | `0.2` | Score ≥ this → 50 % credit; below → 0 % |
| `QUALITY_MEDIUM_FRACTION` | `0.5` | Credit fraction when score is medium |

### Bonuses

| Constant | Default | Description |
|---|---|---|
| `RANDOM_BONUS_CHANCE` | `0.33` | Probability of 1 bonus point per active tick |
| `MYSTERY_BONUS_MIN` | `1` | Minimum mystery bonus points |
| `MYSTERY_BONUS_MAX` | `5` | Maximum mystery bonus points |
| `MYSTERY_BONUS_CUTOFF_HOUR` | `12` | Mystery bonus only before this hour (noon) |

### Streak Freeze & Vacation

| Constant | Default | Description |
|---|---|---|
| `MAX_FREEZES_PER_WEEK` | `1` | Streak freezes allowed per calendar week |
| `VACATION_MAX_DAYS` | `3` | Max consecutive vacation days |

### Daily Target

| Constant | Default | Description |
|---|---|---|
| `DAILY_TARGET_DEFAULT` | `30` | Default daily active-minutes goal |
| `DAILY_TARGET_MIN` | `10` | Minimum daily target |
| `DAILY_TARGET_MAX` | `240` | Maximum daily target (4 hours) |

### Focus Session

| Constant | Default | Description |
|---|---|---|
| `FOCUS_SESSION_MIN_SECONDS` | `1200` | Seconds of uninterrupted activity for one focus session |

### Phone Notification

| Constant | Default | Description |
|---|---|---|
| `PHONE_NOTIFIER_ENABLED` | `False` | Master toggle (also controlled via tray) |
| `PHONE_NOTIFIER_HOUR` | `20` | Hour (24 h) when phone alerts start |
| `PHONE_NOTIFIER_INTERVAL` | `30` | Minutes between repeated phone alerts |
| `NTFY_TOPIC` | env var / `.env` | ntfy.sh topic for phone alerts |
| `NTFY_STATUS_TOPIC` | env var / `.env` | ntfy.sh topic for heartbeats (GitHub Actions) |

### Notifications &amp; Dashboard

| Constant | Default | Description |
|---|---|---|
| `STREAK_RISK_NOTIFICATION_HOUR` | `21` | Hour (24 h) when desktop streak-risk notification fires |
| `NOTIFICATION_DURATION_MS` | `5000` | Desktop notification duration (milliseconds) |
| `DASHBOARD_REFRESH_MS` | `5000` | Dashboard auto-refresh interval (milliseconds) |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **App won't start** | Check `{data_dir}/momentum.log` for errors (`data_dir` is `%APPDATA%\LaptopMomentum` on Windows). |
| **No tray icon** | Try restarting Windows Explorer (Task Manager → Windows Explorer → Restart). |
| **Notifications not showing** | Right-click tray → **Notifications: On**. Windows may also suppress notifications during Focus Assist. |
| **Keyboard/mouse not tracked** | Restart the app. On some systems, pynput hooks need admin privileges. |
| **Dashboard won't open** | Try right-click → **Open Dashboard** (not just middle-click). Check `momentum.log` for crash details. |
| **Phone notification not sending** | Ensure `NTFY_TOPIC` is set in `.env` (next to the EXE or in the project root). Verify the topic name matches what you subscribed to in the ntfy app. Enable **Phone Reminder** in the tray menu. |
| **Sound effects not playing** | Ensure Qt Multimedia is available (the EXE bundles it). Check **Notifications: On** in the tray. The sounds are synthesised WAVs — they play on first milestone/bonus after launch. |
| **Quality indicator always low** | Make sure you're using both keyboard and mouse naturally. Scripted input (e.g. auto-clickers, macro playbacks) will be discounted. |
| **GitHub Actions not running** | Ensure you added `NTFY_TOPIC` and `NTFY_STATUS_TOPIC` as repository secrets. The workflow can also be triggered manually from the Actions tab. |
| **Blue screen / BSOD** | Extremely unlikely to be caused by this app (it's 100% user-mode Python). Run `sfc /scannow` and check your RAM/drivers first. |
| **Two instances on startup** | The registry autostart key and the tray's restart logic may conflict. Manually kill the extra process. |

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | **Python 3.14** |
| GUI | **PySide6** (Qt for Python) |
| Input tracking | **pynput** (global keyboard/mouse hooks) |
| Database | **SQLite 3** (via stdlib `sqlite3`) |
| Audio | **PySide6.QtMultimedia** (synthesised WAV) |
| Notifications | **ntfy.sh** (HTTP POST, no SDK required) |
| Packaging | **PyInstaller** 6.20+ |
| Package manager | **uv** |
| CI (backup check) | **GitHub Actions** (scheduled workflow) |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
