<div align="center">
  <img src="favicon.png" alt="Laptop Momentum" width="96" height="96">
  <h1 align="center">Laptop Momentum</h1>
  <p align="center">
    A local-first background app that tracks daily laptop keyboard &amp; mouse activity<br>
    to build streaks, earn points, and keep you consistent — no accounts, no cloud.
  </p>
</div>

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
  - [Rules](#rules)
  - [Point Calculation](#point-calculation)
  - [Session Bonus](#session-bonus)
  - [Lifelines](#lifelines)
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

- **Real activity tracking** — keyboard and mouse input, not just screen-on time
- **Streak system** — consecutive days with ≥2 active minutes build your streak
- **Point system** — every minute beyond the first 10 earns 1 point
- **Session bonus** — after 30 minutes of uninterrupted activity, every 2 minutes earns 3 points instead of 2
- **Lifelines** — earned by exceeding your weekly target, used to save a broken streak
- **Auto weekly target** — adapts to your performance (no manual fiddling)
- **System tray** — runs silently in the background, right-click for options
- **Dashboard** — real-time timer, streaks, points, weekly progress, activity log
- **Milestone notifications** — streak-safe, now-earning-points, session-bonus, weekly summary
- **Windows startup on login** — optional, toggled from the tray menu
- **4 AM day boundary** — late-night owls keep yesterday's streak alive
- **Fully local** — SQLite database, no internet, no accounts, no telemetry

---

## How It Works

### Rules

| Concept | Detail |
|---|---|
| **Day** | Runs from **04:00** to the next day **03:59**. Activity before 4 AM counts toward the *previous* day. |
| **Week** | Runs from **Monday 04:00** to the next Monday **03:59**. |
| **Streak** | Every day with **≥2 active minutes** extends your streak by 1. Days below 2 minutes break it (unless saved by a lifeline). |
| **Points** | **0 points** for the first 10 minutes each day. **1 point per minute** after that. |
| **Session Bonus** | After **30 uninterrupted minutes**, every **2 minutes = 3 points** (instead of 2). Bonus resets when you go idle for ≥60 seconds. |
| **Lifelines** | **1 lifeline** per 10 points *over* the weekly target at the week boundary. Max 3. Automatically saves a missed streak day. |
| **Weekly Target** | Calculated **automatically** each Monday (you cannot set it manually). Based on your last 4 weeks, streak, momentum, and a weak-week reduction. |

### Point Calculation

```
base_points = max(0, active_minutes_today - 10)
bonus_points = (uninterrupted_seconds_beyond_1800 // 120) * 1   # awarded every 2 min
total_points_today = base_points + bonus_points
```

**Example:** 45 minutes of activity, 25 of which were part of a 35-minute uninterrupted session:

- Base: `45 - 10 = 35 points`
- Bonus: 5 minutes beyond the 30-minute threshold → `(300 // 120) = 2 bonus points`
- Total: **37 points**

### Session Bonus

If you stay active without a 60-second idle gap for ≥30 minutes:
- A notification fires: **"Session Bonus Active"**
- Every subsequent 2 minutes of continued activity awards **1 bonus point** (3 points per 2 minutes instead of 2)
- Going idle for 60 seconds resets the session counter; you need another 30 uninterrupted minutes to re-trigger

### Lifelines

- Earned at the week boundary: every 10 points over target = 1 lifeline (max 3)
- If a day ends with <2 active minutes AND you have an active streak, a lifeline is consumed automatically to protect the streak
- If no lifelines are available, the streak breaks

### Weekly Target (Auto)

Recalculated every Monday 04:00 using:

```
base            = average points of last 4 weeks (or 500 if no history)
streak_bonus    = min(current_streak × 5, +50)
momentum_bonus  = (last_week_points - last_target) × 0.1   (only if positive)
weak_reduction  = -(last_target × 0.1)                      (only if last week < 50% of target)
target          = clamp(base + streak_bonus + momentum_bonus - weak_reduction, 100, 2000)
```

---

## Architecture

```
laptop-momentum/
├── main.py                     # Entry point, console hiding, startup wiring
├── pyproject.toml              # Dependencies (PySide6, pynput, PyInstaller)
├── favicon.ico / favicon.png   # Application icons
├── build/
│   └── laptop-momentum.spec    # PyInstaller spec (builds the EXE)
├── app/
│   ├── __init__.py
│   ├── config.py               # Constants (day boundary, thresholds, etc.)
│   ├── database.py             # Thread-safe SQLite wrapper
│   ├── input_tracker.py        # pynput-based keyboard/mouse listener
│   ├── activity_monitor.py     # Central coordinator (10s tick loop)
│   ├── points_manager.py       # Point calculation & auto-target formula
│   ├── streak_manager.py       # Streak state machine
│   ├── lifeline_manager.py     # Lifeline earn/consume logic
│   ├── notification_manager.py # Desktop notifications via tray
│   ├── autostart_manager.py    # Windows registry startup toggle
│   └── ui/
│       ├── dashboard.py        # Scrollable stats window (real-time timer)
│       └── tray.py             # System tray icon, context menu
```

### Data Flow

```
InputTracker (pynput hooks)
    ↓  is_active() every 10s
ActivityMonitor._on_tick()
    ↓  checkpoint every 60s
Database (SQLite, `%APPDATA%\LaptopMomentum\momentum.db`)
    ↓  state_updated Signal
TrayIcon (tooltip)  &  Dashboard (stats window)
```

---

## For Users: Running on Any PC

### Option A — Download the Pre-Built EXE (Recommended)

1. Grab `LaptopMomentum.exe` from the latest [Releases](https://github.com/YOUR_USER/YOUR_REPO/releases) page.
2. Place it anywhere you like (e.g. `C:\Program Files\LaptopMomentum\`).
3. Double-click `LaptopMomentum.exe`. It runs silently in the system tray (bottom-right taskbar).

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

| Constant | Default | Description |
|---|---|---|
| `DAY_BOUNDARY_HOUR` | `4` | Hour (24h) when a new day starts |
| `IDLE_TIMEOUT_SECONDS` | `60` | Seconds of no input before considered idle |
| `TICK_INTERVAL_SECONDS` | `10` | Activity monitor loop interval |
| `STREAK_MINIMUM_MINUTES` | `2` | Minimum active minutes for a streak day |
| `POINTS_THRESHOLD_MINUTES` | `10` | Minutes before points start accruing |
| `MAX_LIFELINES` | `3` | Maximum lifelines a user can hold |
| `DEFAULT_WEEKLY_TARGET` | `500` | Fallback weekly target when no history |
| `BONUS_SESSION_MIN_SECONDS` | `1800` | Seconds of consecutive activity to trigger bonus |
| `BONUS_INTERVAL_SECONDS` | `120` | Bonus award interval (seconds) |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **App won't start** | Check `%APPDATA%\LaptopMomentum\momentum.log` for errors. |
| **No tray icon** | Try restarting Windows Explorer (Task Manager → Windows Explorer → Restart). |
| **Notifications not showing** | Right-click tray → **Notifications: On**. Windows may also suppress notifications during Focus Assist. |
| **Keyboard/mouse not tracked** | Restart the app. On some systems, pynput hooks need admin privileges. |
| **Dashboard won't open** | Try right-click → **Open Dashboard** (not just middle-click). Check `momentum.log` for crash details. |
| **Blue screen / BSOD** | Extremely unlikely to be caused by this app (it's 100% user-mode Python). Run `sfc /scannow` and check your RAM/drivers first. If you suspect pynput hooks, switch to `GetLastInputInfo` mode. |
| **Two instances on startup** | The registry autostart key and the tray's restart logic may conflict. Manually kill the extra process. |

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | **Python 3.14** |
| GUI | **PySide6** (Qt for Python) |
| Input tracking | **pynput** (global keyboard/mouse hooks) |
| Database | **SQLite 3** (via stdlib `sqlite3`) |
| Packaging | **PyInstaller** 6.20+ |
| Package manager | **uv** |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
