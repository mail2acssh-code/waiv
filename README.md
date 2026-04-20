# ✋ Waiv

> Wave at your Mac to control it.

Waiv uses your webcam to detect hand gestures and control media, volume, mic, and more — entirely on-device, no cloud, no account. Lives in the menu bar and starts at login.

**[Website](https://mail2acssh-code.github.io/waiv)** · **[Download DMG](https://github.com/mail2acssh-code/waiv/releases/latest/download/Waiv.dmg)** · **[Report a Bug](https://github.com/mail2acssh-code/waiv/issues)**

---

## Gestures

Hold any gesture steady for **2 seconds** to fire it.

| Gesture | Action |
|---|---|
| 👍 Thumbs Up | Volume Up |
| 👎 Thumbs Down | Volume Down |
| ✋ Open Palm | Play / Pause |
| 👉 Thumb Right | Next Track |
| 👈 Thumb Left | Previous Track |
| 🖕 Middle Finger | Lock Screen |
| ☝️ Index Up | Toggle Mic Mute |
| 🤙 Pinky Up | Quit Waiv |

Works with Spotify, Apple Music, YouTube, Netflix, and any app with a system media session.

---

## Install (non-technical users)

1. [Download Waiv.dmg](https://github.com/mail2acssh-code/waiv/releases/latest/download/Waiv.dmg)
2. Open the DMG → drag **Waiv** to Applications
3. **First launch — bypass Gatekeeper:** right-click **Waiv.app** → **Open** → click **Open** in the dialog.
   *(macOS blocks unsigned apps by default. You only need to do this once.)*
   - Alternatively: **System Settings → Privacy & Security** → scroll down → **Open Anyway**
4. Grant camera access when prompted (**System Settings → Privacy & Security → Camera**)

The ✋ icon appears in your menu bar when Waiv is running.

---

## Install (developers)

```bash
# Clone
git clone https://github.com/mail2acssh-code/waiv waiv
cd waiv

# Creates venv, downloads the hand-landmark model, installs the LaunchAgent
bash install.sh
```

**Requirements:** macOS 12 Monterey or later · Python 3.10+ · Webcam

**Manage the agent:**
```bash
# Logs
tail -f /tmp/waiv.log

# Stop
launchctl unload ~/Library/LaunchAgents/com.waiv.gesture.plist

# Start
launchctl load ~/Library/LaunchAgents/com.waiv.gesture.plist

# Uninstall
bash uninstall.sh
```

---

## Plugin System

Drop a `.py` file into the `plugins/` folder to add gesture controls for any app. Waiv auto-loads all plugins at startup — no registration needed.

### How it works

- Plugins **without** `is_active()` are always loaded (unconditional defaults)
- Plugins **with** `is_active()` override defaults only when their app is running
- When the app quits, Waiv falls back to defaults automatically

### Write a plugin

```python
# plugins/myapp.py
import subprocess

def is_active() -> bool:
    """Return True while your app is running."""
    r = subprocess.run(
        ["osascript", "-e", '(name of processes) contains "MyApp"'],
        capture_output=True, text=True
    )
    return r.stdout.strip() == "true"

def _do_something():
    subprocess.run(["osascript", "-e", 'tell application "MyApp" to ...'])

GESTURE_ACTIONS = {
    "open_palm": _do_something,
    "thumbs_up": _do_something,
}
```

### Available gesture constants

```python
from gesture_classifier import (
    GESTURE_THUMBS_UP,      # "thumbs_up"
    GESTURE_THUMBS_DOWN,    # "thumbs_down"
    GESTURE_THUMB_LEFT,     # "thumb_left"
    GESTURE_THUMB_RIGHT,    # "thumb_right"
    GESTURE_OPEN_PALM,      # "open_palm"
    GESTURE_MIDDLE_FINGER,  # "middle_finger"
    GESTURE_INDEX_UP,       # "index_up"
    GESTURE_PINKY_UP,       # "pinky_up"
)
```

See [`plugins/zoom.py`](plugins/zoom.py) for a complete example.

**To contribute a plugin:** fork the repo, add your file to `plugins/`, and open a pull request.

---

## Build the DMG yourself

```bash
# Install build deps (once)
pip install py2app

# Build Waiv.app and package as Waiv-1.0.0.dmg
bash build_dmg.sh 1.0.0
```

Output: `dist/Waiv-1.0.0.dmg`

---

## How it works

Gesture detection uses [MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) to track 21 hand landmarks in real time. Classification is pure geometry on those landmarks — no secondary ML model, no API calls, zero data leaves your machine.

The app runs as a macOS LaunchAgent (background process managed by `launchd`). It sleeps automatically when no media is playing to keep CPU usage near zero.

---

## License

[MIT](LICENSE)
