"""
Zoom plugin — overrides gestures when a Zoom meeting is running.

Active only while the zoom.us process is running; falls back to
media_player defaults the moment you quit Zoom.

Overrides
---------
  ✋  open_palm  → toggle Zoom video    (⌘⇧V)
  ☝️  index_up   → toggle Zoom mic      (⌘⇧A)

All other gestures (volume, skip track, lock screen, quit) remain as
media_player defines them.
"""

import subprocess


def is_active() -> bool:
    """True while the Zoom.us app process is running."""
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to '
             '(name of processes) contains "zoom.us"'],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


def _zoom_keystroke(key: str, modifiers: str):
    subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to keystroke "{key}" '
         f"using {{{modifiers}}}"],
        capture_output=True, timeout=3,
    )


def _toggle_video():
    _zoom_keystroke("v", "command down, shift down")


def _toggle_mic():
    _zoom_keystroke("a", "command down, shift down")


GESTURE_ACTIONS = {
    "open_palm": _toggle_video,
    "index_up":  _toggle_mic,
}
