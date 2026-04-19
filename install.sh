#!/bin/bash
# Waiv Gesture Control — full install from a fresh git clone
#
# What this does:
#   1. Creates a Python virtual environment
#   2. Installs Python dependencies
#   3. Downloads the MediaPipe hand-landmark model (~29 MB)
#   4. Generates a LaunchAgent plist with the correct paths for this machine
#   5. Prompts macOS for camera permission
#   6. Installs and starts the LaunchAgent (runs at login)
#
# Usage:
#   git clone <repo-url> waiv
#   cd waiv
#   bash install.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_NAME="com.waiv.gesture.plist"
MODEL_FILE="hand_landmarker.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

# ── Step 1: Python ────────────────────────────────────────────────────────────
echo "==> Checking Python..."
if command -v python3.11 &>/dev/null; then
    PYTHON=python3.11
elif command -v python3 &>/dev/null; then
    PYTHON=python3
else
    echo "ERROR: Python 3 not found."
    echo "Install via Homebrew:  brew install python"
    echo "Or from:               https://www.python.org/downloads/"
    exit 1
fi
echo "    $($PYTHON --version)"

# ── Step 2: virtual environment ───────────────────────────────────────────────
echo "==> Setting up virtual environment..."
if [ ! -d venv ]; then
    $PYTHON -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "    Dependencies installed."

# ── Step 3: hand-landmark model ───────────────────────────────────────────────
if [ ! -f "$MODEL_FILE" ]; then
    echo "==> Downloading hand-landmark model (~29 MB)..."
    curl -L --progress-bar "$MODEL_URL" -o "$MODEL_FILE"
else
    echo "==> Model file already present, skipping download."
fi

# ── Step 4: generate plist with paths for this machine ───────────────────────
PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
echo "==> Writing LaunchAgent plist..."
cat > "$PLIST_NAME" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.waiv.gesture</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$SCRIPT_DIR/gesture_app.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>

    <!-- Start automatically at login -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Don't restart on crash/error (exit code != 0) -->
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/waiv.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/waiv-error.log</string>
</dict>
</plist>
PLIST_EOF

# ── Step 5: camera permission ─────────────────────────────────────────────────
echo "==> Checking camera permission..."
echo "    (A brief window may appear — this is normal)"
timeout 4 "$PYTHON_BIN" gesture_app.py --always-active 2>&1 \
    | grep -E "Camera ready|Cannot open|permission" || true

# ── Step 6: install LaunchAgent ───────────────────────────────────────────────
echo "==> Installing LaunchAgent..."
mkdir -p "$LAUNCH_AGENTS"
cp "$PLIST_NAME" "$LAUNCH_AGENTS/"
launchctl unload "$LAUNCH_AGENTS/$PLIST_NAME" 2>/dev/null || true
launchctl load   "$LAUNCH_AGENTS/$PLIST_NAME"

echo ""
echo "Done. Waiv is now running in the background."
echo ""
echo "  Logs    tail -f /tmp/waiv.log"
echo "  Stop    launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  Start   launchctl load   ~/Library/LaunchAgents/$PLIST_NAME"
echo "  Uninstall  bash uninstall.sh"
echo ""
echo "If you see a camera-permission error:"
echo "  System Settings > Privacy & Security > Camera > enable Python"
