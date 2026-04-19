"""
macOS media and volume controller.
All actions are executed via osascript (AppleScript) — no extra Python
dependencies, no network calls.

Media key codes (NX_KEYTYPE_*):
  16 = Play/Pause
  17 = Next
  18 = Previous
  19 = Fast Forward
  20 = Rewind

Volume is 0–100 (macOS "output volume").
"""

import subprocess
import logging

log = logging.getLogger(__name__)


_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"

def _notify(title: str, message: str = ""):
    """Post a macOS notification via terminal-notifier (best-effort)."""
    try:
        subprocess.run(
            [_NOTIFIER,
             "-title",   "Waiv",
             "-subtitle", title,
             "-message",  message or " ",
             "-sound",    "Glass"],
            capture_output=True, timeout=3
        )
    except Exception:
        pass

# Volume step per thumbs up/down gesture
VOLUME_STEP = 5


def _osascript(script: str) -> str:
    """Run an AppleScript snippet and return stdout (stripped)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            log.debug("osascript error: %s", result.stderr.strip())
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.warning("osascript timed out")
        return ""
    except Exception as e:
        log.warning("osascript failed: %s", e)
        return ""


def warmup():
    """Run a no-op Swift snippet to warm the compiler cache."""
    try:
        subprocess.run(
            ["swift", "-"],
            input="import Foundation",
            text=True, capture_output=True, timeout=10
        )
        log.debug("Swift warmed up")
    except Exception:
        pass


def _send_media_key(key_code: int):
    """
    Post a HID-level media key event via Swift + CGEventPost.
    This reaches the system media session (Chrome/YouTube, Safari, etc.)
    without requiring the target app to be focused.

    NX_KEYTYPE values: 16=play/pause  17=next  18=previous
    """
    swift = f"""
import AppKit
func send(_ code: Int32, down: Bool) {{
    let d1 = Int((code << 16) | ((down ? 0xa : 0xb) << 8))
    if let e = NSEvent.otherEvent(with: .systemDefined, location: .zero,
        modifierFlags: down ? .function : [], timestamp: 0,
        windowNumber: 0, context: nil, subtype: 8, data1: d1, data2: -1) {{
        e.cgEvent?.post(tap: .cghidEventTap)
    }}
}}
send({key_code}, down: true)
send({key_code}, down: false)
"""
    try:
        subprocess.run(
            ["swift", "-"],
            input=swift, text=True,
            capture_output=True, timeout=5
        )
    except Exception as e:
        log.warning("swift media key failed: %s", e)


# ------------------------------------------------------------------
# Volume
# ------------------------------------------------------------------

def get_volume() -> int:
    """Return current output volume 0–100."""
    result = _osascript("output volume of (get volume settings)")
    try:
        return int(result)
    except ValueError:
        return 50


def set_volume(level: int):
    level = max(0, min(100, level))
    _osascript(f"set volume output volume {level}")
    log.info("Volume set to %d", level)


# ------------------------------------------------------------------
# Playback — HID media keys reach any app with an active media session
# (Spotify, YouTube in Chrome/Safari, Apple Music, etc.)
# ------------------------------------------------------------------


def volume_up():
    current = get_volume()
    set_volume(current + VOLUME_STEP)


def volume_down():
    current = get_volume()
    set_volume(current - VOLUME_STEP)


def play_pause():
    _send_media_key(16)
    log.info("play/pause")


def next_track():
    _send_media_key(17)
    log.info("next track")


def prev_track():
    _send_media_key(18)
    log.info("previous track")


# ------------------------------------------------------------------
# Mic mute toggle
# ------------------------------------------------------------------

_mic_muted = False

def mic_toggle():
    global _mic_muted
    _mic_muted = not _mic_muted
    level = 0 if _mic_muted else 100
    _osascript(f"set volume input volume {level}")
    log.info("Mic Muted" if _mic_muted else "Mic Unmuted")


# ------------------------------------------------------------------
# Easter egg
# ------------------------------------------------------------------

def lock_screen():
    log.info("Easter egg: locking screen")
    _osascript(
        'tell application "System Events" to '
        'keystroke "q" using {command down, control down}'
    )


# ------------------------------------------------------------------
# Quit Waiv
# ------------------------------------------------------------------

def quit_app():
    import os as _os
    import time as _time
    log.info("Quitting Waiv via pinky gesture")
    _notify("Waiv Stopping", "Goodbye.")
    # Unload the LaunchAgent so it doesn't restart
    subprocess.run(
        ["launchctl", "unload",
         _os.path.expanduser("~/Library/LaunchAgents/com.waiv.gesture.plist")],
        capture_output=True
    )
    # Import lazily to avoid circular import; trigger the same clean shutdown
    # path that the menu's Quit uses (sets stop event, then quits rumps).
    try:
        import gesture_app as _app
        from PyObjCTools import AppHelper
        _app._stop_evt.set()
        _time.sleep(0.4)
        AppHelper.callAfter(lambda: __import__("rumps").quit_application())
    except Exception:
        import signal as _signal
        _os.kill(_os.getpid(), _signal.SIGTERM)


# ------------------------------------------------------------------
# Dispatch — delegates to plugin_loader so plugins in plugins/ are
# auto-discovered and merged at runtime.
# ------------------------------------------------------------------

def execute(gesture: str):
    import plugin_loader
    action = plugin_loader.get_action(gesture)
    if action:
        action()
