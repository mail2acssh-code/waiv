"""
Waiv launcher — entry point for the .app bundle.

On first run:
  1. Installs the LaunchAgent plist → ~/Library/LaunchAgents/
  2. Loads it (starts background gesture loop)
  3. Shows a notification and exits

On subsequent runs (LaunchAgent already installed):
  Just shows a "Waiv is running" notification and exits.

The actual gesture loop lives in gesture_app.py and is managed by launchd.
"""

import os
import subprocess
import sys
import plistlib
import shutil

BUNDLE_ID   = "com.waiv.gesture"
PLIST_NAME  = f"{BUNDLE_ID}.plist"
LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
PLIST_DEST  = os.path.join(LAUNCH_AGENTS, PLIST_NAME)

# Paths inside the .app bundle
BUNDLE_RES  = os.path.dirname(os.path.abspath(__file__))
PYTHON_BIN  = sys.executable
GESTURE_APP = os.path.join(BUNDLE_RES, "gesture_app.py")
NOTIFIER    = "/opt/homebrew/bin/terminal-notifier"


def notify(title: str, message: str = ""):
    try:
        if os.path.exists(NOTIFIER):
            subprocess.run([NOTIFIER,
                            "-title", "Waiv",
                            "-subtitle", title,
                            "-message", message or " ",
                            "-sound", "Glass"],
                           capture_output=True, timeout=5)
        else:
            subprocess.run(["osascript", "-e",
                            f'display notification "{message}" '
                            f'with title "Waiv" subtitle "{title}"'],
                           capture_output=True, timeout=3)
    except Exception:
        pass


def is_agent_loaded() -> bool:
    result = subprocess.run(
        ["launchctl", "list", BUNDLE_ID],
        capture_output=True, text=True
    )
    return result.returncode == 0


def install_agent():
    plist = {
        "Label": BUNDLE_ID,
        "ProgramArguments": [PYTHON_BIN, GESTURE_APP, "--always-active"],
        "WorkingDirectory": BUNDLE_RES,
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": "/tmp/waiv.log",
        "StandardErrorPath": "/tmp/waiv-error.log",
    }
    os.makedirs(LAUNCH_AGENTS, exist_ok=True)
    with open(PLIST_DEST, "wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "unload", PLIST_DEST],
                   capture_output=True)
    subprocess.run(["launchctl", "load", PLIST_DEST],
                   capture_output=True)


def main():
    if is_agent_loaded():
        notify("Already running", "Waiv is active in the background.")
        return

    notify("Starting up…", "Installing Waiv gesture control.")
    install_agent()

    import time
    time.sleep(2)

    if is_agent_loaded():
        notify("Waiv is running", "Show your hand to the camera to control media.")
    else:
        notify("Setup issue", "Check System Settings > Privacy > Camera and allow Python.")


if __name__ == "__main__":
    main()
