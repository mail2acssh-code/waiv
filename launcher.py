"""
Waiv launcher — entry point for the .app bundle.

Modes:
  --daemon   : called by launchd — skip installer, run gesture loop directly
  (no args)  : opened by user — install/upgrade agent, then exit

Install logic:
  - If agent not installed: fresh install (writes plist, loads agent)
  - If agent installed with stale plist: auto-upgrade silently
  - If agent installed and current: show "already running" hint
"""

import os
import subprocess
import sys
import plistlib
import time

BUNDLE_ID     = "com.waiv.gesture"
PLIST_NAME    = f"{BUNDLE_ID}.plist"
LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
PLIST_DEST    = os.path.join(LAUNCH_AGENTS, PLIST_NAME)

BUNDLE_RES   = os.path.dirname(os.path.abspath(__file__))
BUNDLE_MACOS = os.path.join(os.path.dirname(BUNDLE_RES), "MacOS")
WAIV_BIN     = os.path.join(BUNDLE_MACOS, "Waiv")
PYTHON_BIN   = sys.executable
GESTURE_APP  = os.path.join(BUNDLE_RES, "gesture_app.py")
NOTIFIER     = "/opt/homebrew/bin/terminal-notifier"


def notify(title: str, message: str = ""):
    try:
        if os.path.exists(NOTIFIER):
            subprocess.run(
                [NOTIFIER, "-title", "Waiv", "-subtitle", title,
                 "-message", message or " ", "-sound", "Glass"],
                capture_output=True, timeout=5,
            )
        else:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "Waiv" subtitle "{title}"'],
                capture_output=True, timeout=3,
            )
    except Exception:
        pass


def is_agent_loaded() -> bool:
    r = subprocess.run(["launchctl", "list", BUNDLE_ID],
                       capture_output=True, text=True)
    return r.returncode == 0


def plist_is_current() -> bool:
    """True if installed plist points to this Waiv binary with --daemon flag."""
    if not os.path.exists(PLIST_DEST):
        return False
    try:
        with open(PLIST_DEST, "rb") as f:
            p = plistlib.load(f)
        args = p.get("ProgramArguments", [])
        return (len(args) >= 2
                and args[0] == WAIV_BIN
                and "--daemon" in args)
    except Exception:
        return False


def request_camera_permission() -> bool:
    """
    Briefly open the camera from the .app bundle context to trigger the TCC
    permission dialog.  Must be called from a visible .app process.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        opened = cap.isOpened()
        cap.release()
        return opened
    except Exception:
        return True


def install_agent():
    """Write (or overwrite) the plist and reload the agent."""
    plist = {
        "Label": BUNDLE_ID,
        "ProgramArguments": [WAIV_BIN, "--daemon"],
        "WorkingDirectory": BUNDLE_RES,
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath":  "/tmp/waiv.log",
        "StandardErrorPath": "/tmp/waiv-error.log",
    }
    os.makedirs(LAUNCH_AGENTS, exist_ok=True)
    with open(PLIST_DEST, "wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "unload", PLIST_DEST], capture_output=True)
    time.sleep(0.5)
    subprocess.run(["launchctl", "load",   PLIST_DEST], capture_output=True)


def main():
    # ── Daemon mode: called by launchd ────────────────────────────────────────
    if "--daemon" in sys.argv:
        import runpy
        sys.argv = [GESTURE_APP, "--always-active"]
        runpy.run_path(GESTURE_APP, run_name="__main__")
        return

    # ── GUI mode: user opened Waiv.app ────────────────────────────────────────
    loaded = is_agent_loaded()
    current = plist_is_current()

    if loaded and current:
        # Already running with correct config — nothing to do
        notify("Waiv is running",
               "Use the ✋ menu bar icon · 'Show Setup…' to check permissions.")
        return

    if loaded and not current:
        # Old plist format (python -c ...) or wrong binary path — upgrade silently
        notify("Updating Waiv…", "Restarting with latest configuration.")
        install_agent()
        time.sleep(2)
        notify("Waiv Updated", "Now running as Waiv. Check System Settings → Privacy if needed.")
        return

    # Not loaded — fresh install or user reinstalling after deletion
    notify("Starting Waiv…", "The setup wizard will guide you through permissions.")
    install_agent()
    time.sleep(2)

    if is_agent_loaded():
        notify("Waiv is starting…", "Complete the setup wizard to finish installation.")
    else:
        notify("Setup issue", "Relaunch Waiv.app to try again.")


if __name__ == "__main__":
    main()
