"""
Waiv plugins package.

Each .py file here is auto-loaded at startup. See plugin_loader.py for the
full protocol and plugins/media_player.py for the canonical example.

Quick-start
-----------
1. Copy plugins/media_player.py as a starting point.
2. Add an is_active() function that returns True only when your target app
   is running (see plugins/zoom.py for an example).
3. Define GESTURE_ACTIONS mapping gesture constants → callables.
4. Drop the file in this directory — no registration needed.

Gesture constants (import from gesture_classifier):
  GESTURE_THUMBS_UP     "thumbs_up"
  GESTURE_THUMBS_DOWN   "thumbs_down"
  GESTURE_THUMB_LEFT    "thumb_left"
  GESTURE_THUMB_RIGHT   "thumb_right"
  GESTURE_OPEN_PALM     "open_palm"
  GESTURE_MIDDLE_FINGER "middle_finger"
  GESTURE_INDEX_UP      "index_up"
  GESTURE_PINKY_UP      "pinky_up"
"""
