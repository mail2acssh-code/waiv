"""
Default media & system plugin — provides the built-in gesture actions.

This plugin has no is_active() guard, so it is always loaded as the
baseline. App-specific plugins can override any gesture by defining
is_active() + the same gesture key in their own GESTURE_ACTIONS dict.

Gesture → action
----------------
  thumbs_up      → volume up
  thumbs_down    → volume down
  open_palm      → play / pause
  thumb_right    → next track
  thumb_left     → previous track
  middle_finger  → lock screen
  index_up       → toggle mic mute
  pinky_up       → quit Waiv
"""

import media_controller as mc
from gesture_classifier import (
    GESTURE_THUMBS_UP,
    GESTURE_THUMBS_DOWN,
    GESTURE_THUMB_LEFT,
    GESTURE_THUMB_RIGHT,
    GESTURE_OPEN_PALM,
    GESTURE_MIDDLE_FINGER,
    GESTURE_INDEX_UP,
    GESTURE_PINKY_UP,
)

GESTURE_ACTIONS = {
    GESTURE_THUMBS_UP:     mc.volume_up,
    GESTURE_THUMBS_DOWN:   mc.volume_down,
    GESTURE_OPEN_PALM:     mc.play_pause,
    GESTURE_THUMB_RIGHT:   mc.next_track,
    GESTURE_THUMB_LEFT:    mc.prev_track,
    GESTURE_MIDDLE_FINGER: mc.lock_screen,
    GESTURE_INDEX_UP:      mc.mic_toggle,
    GESTURE_PINKY_UP:      mc.quit_app,
}
