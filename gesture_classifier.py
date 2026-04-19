"""
Gesture classifier using MediaPipe hand landmarks.
All detection is pure geometry on the 21-point hand skeleton — no ML inference,
no API calls, zero tokens.

Landmark index reference (MediaPipe):
  0  = WRIST
  1  = THUMB_CMC
  2  = THUMB_MCP
  3  = THUMB_IP
  4  = THUMB_TIP
  5  = INDEX_FINGER_MCP
  6  = INDEX_FINGER_PIP
  7  = INDEX_FINGER_DIP
  8  = INDEX_FINGER_TIP
  9  = MIDDLE_FINGER_MCP
  10 = MIDDLE_FINGER_PIP
  11 = MIDDLE_FINGER_DIP
  12 = MIDDLE_FINGER_TIP
  13 = RING_FINGER_MCP
  14 = RING_FINGER_PIP
  15 = RING_FINGER_DIP
  16 = RING_FINGER_TIP
  17 = PINKY_MCP
  18 = PINKY_PIP
  19 = PINKY_DIP
  20 = PINKY_TIP

Coordinate system: x increases rightward, y increases downward (image coords).

Orientation-independence:
  The original palm-facing approach used tip.y > pip.y to detect folded fingers.
  This fails when the back of the hand faces the camera because curled fingers
  project *toward* the camera and their tips can appear *above* their PIP joints.

  Fix: use wrist-relative 2D distance instead.
    - Extended finger: tip is ~2-3x further from wrist than its MCP joint.
    - Folded finger:   tip and MCP are roughly equidistant from wrist.
  This metric is consistent regardless of hand rotation around the vertical axis.
"""

import time
import math

# Gesture constants
GESTURE_THUMBS_UP     = "thumbs_up"
GESTURE_THUMBS_DOWN   = "thumbs_down"
GESTURE_THUMB_LEFT    = "thumb_left"
GESTURE_THUMB_RIGHT   = "thumb_right"
GESTURE_OPEN_PALM     = "open_palm"
GESTURE_MIDDLE_FINGER = "middle_finger"
GESTURE_INDEX_UP      = "index_up"
GESTURE_PINKY_UP      = "pinky_up"
GESTURE_NONE          = None

# How long a gesture must be held before it fires (seconds)
HOLD_DURATION = 2.0
# Cooldown between repeated fires of the same gesture (seconds)
COOLDOWN = 1.2


class GestureClassifier:
    def __init__(self):
        self._candidate_gesture = None
        self._candidate_since = 0.0
        self._hold_fired = False   # True once the current hold has fired

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, landmarks) -> str | None:
        """
        Returns a gesture constant exactly once per distinct hold.
        The gesture must be released (hand down / different pose) before
        the same or any other gesture can fire again.
        """
        if landmarks is None:
            self._candidate_gesture = None
            self._hold_fired = False
            return None

        raw = self._classify_raw(landmarks)
        now = time.monotonic()

        if raw != self._candidate_gesture:
            # Gesture changed — start a fresh hold window
            self._candidate_gesture = raw
            self._candidate_since = now
            self._hold_fired = False
            return None

        if raw is None or self._hold_fired:
            return None

        if now - self._candidate_since < HOLD_DURATION:
            return None

        # Held long enough and hasn't fired yet — fire exactly once
        self._hold_fired = True
        return raw

    # ------------------------------------------------------------------
    # Internal geometry
    # ------------------------------------------------------------------

    def _classify_raw(self, lm) -> str | None:
        """Classify a single frame's landmarks without debouncing."""
        fingers_folded = self._all_fingers_folded(lm)
        thumb_dir = self._thumb_direction(lm)

        if fingers_folded and thumb_dir == "up":
            return GESTURE_THUMBS_UP
        if fingers_folded and thumb_dir == "down":
            return GESTURE_THUMBS_DOWN
        if fingers_folded and thumb_dir == "right":
            return GESTURE_THUMB_RIGHT
        if fingers_folded and thumb_dir == "left":
            return GESTURE_THUMB_LEFT
        if self._is_open_palm(lm):
            return GESTURE_OPEN_PALM
        if self._is_middle_finger(lm):
            return GESTURE_MIDDLE_FINGER
        if self._is_index_up(lm):
            return GESTURE_INDEX_UP
        if self._is_pinky_up(lm):
            return GESTURE_PINKY_UP

        return GESTURE_NONE

    # --- Distance helper ---

    @staticmethod
    def _dist(a, b) -> float:
        """2D Euclidean distance between two landmarks."""
        return math.hypot(a.x - b.x, a.y - b.y)

    # --- Finger state helpers (orientation-independent) ---

    def _finger_extended(self, lm, tip_idx, mcp_idx) -> bool:
        """
        A finger is extended when its tip is significantly further from the
        wrist than its MCP joint.  Works for both palm-facing and back-facing
        because we measure 2D distance in image space rather than relying on
        the y-axis relationship between tip and PIP (which flips when the hand
        is rotated).

        Threshold 1.5× MCP distance:
          - Extended tip ≈ 2.0–2.8× MCP distance from wrist
          - Folded tip   ≈ 0.8–1.2× MCP distance from wrist
        """
        wrist = lm[0]
        d_tip = self._dist(lm[tip_idx], wrist)
        d_mcp = self._dist(lm[mcp_idx], wrist)
        return d_tip > d_mcp * 1.5

    def _all_fingers_folded(self, lm) -> bool:
        """Index, middle, ring, pinky all folded — orientation-independent."""
        # (tip_idx, mcp_idx)
        pairs = [(8, 5), (12, 9), (16, 13), (20, 17)]
        return not any(self._finger_extended(lm, tip, mcp) for tip, mcp in pairs)

    def _is_open_palm(self, lm) -> bool:
        """
        All four fingers clearly extended AND tips are above the wrist.
        The 'above wrist' check keeps this from firing when the hand is held
        horizontally or when showing a fist from the side.
        """
        pairs = [(8, 5), (12, 9), (16, 13), (20, 17)]
        all_extended = all(self._finger_extended(lm, tip, mcp) for tip, mcp in pairs)
        if not all_extended:
            return False

        # Average fingertip y must be above wrist (lower y value in image coords)
        avg_tip_y = sum(lm[t].y for t, _ in pairs) / 4
        return avg_tip_y < lm[0].y - 0.05

    def _is_middle_finger(self, lm) -> bool:
        """
        Middle finger extended, all others (index, ring, pinky) folded.
        Tip must be above wrist so a sideways fist doesn't trigger it.
        Thumb position is ignored — tucked or out, doesn't matter.
        """
        middle_up = self._finger_extended(lm, 12, 9)
        others_down = (
            not self._finger_extended(lm, 8,  5) and  # index
            not self._finger_extended(lm, 16, 13) and # ring
            not self._finger_extended(lm, 20, 17)     # pinky
        )
        pointing_up = lm[12].y < lm[0].y - 0.05
        return middle_up and others_down and pointing_up

    def _is_index_up(self, lm) -> bool:
        """
        Index finger extended upward, middle + ring + pinky folded.
        Thumb position ignored. The universal 'shh / quiet' gesture.
        """
        index_up   = self._finger_extended(lm, 8, 5)
        others_down = (
            not self._finger_extended(lm, 12, 9)  and  # middle
            not self._finger_extended(lm, 16, 13) and  # ring
            not self._finger_extended(lm, 20, 17)      # pinky
        )
        pointing_up = lm[8].y < lm[0].y - 0.05
        return index_up and others_down and pointing_up

    def _is_pinky_up(self, lm) -> bool:
        """
        Pinky finger extended upward, index + middle + ring folded.
        Thumb position ignored. Used as the 'quit Waiv' gesture.
        """
        pinky_up   = self._finger_extended(lm, 20, 17)
        others_down = (
            not self._finger_extended(lm, 8,  5)  and  # index
            not self._finger_extended(lm, 12, 9)  and  # middle
            not self._finger_extended(lm, 16, 13)      # ring
        )
        pointing_up = lm[20].y < lm[0].y - 0.05
        return pinky_up and others_down and pointing_up

    # --- Thumb direction ---

    def _thumb_direction(self, lm) -> str:
        """
        Direction the thumb is pointing in image space.

        Uses the wrist→tip vector (lm[0]→lm[4]) rather than MCP→tip.
        The longer baseline makes the angle estimate more stable, especially
        when the hand is rotated (back-facing) and the MCP sits close to the
        wrist in 2D projection.

        Returns: "up", "down", "left", "right", or "none"
        """
        wrist = lm[0]
        tip   = lm[4]
        mcp   = lm[2]

        # Primary vector: wrist → tip (stable, long baseline)
        dx = tip.x - wrist.x
        dy = tip.y - wrist.y

        # Minimum distance from wrist to consider the thumb actually extended
        min_displacement = 0.12  # ~12% of normalised frame width

        if math.hypot(dx, dy) < min_displacement:
            return "none"

        # Sanity: thumb tip must be further from wrist than thumb MCP,
        # i.e. thumb is genuinely extended and not tucked in.
        if self._dist(tip, wrist) < self._dist(mcp, wrist) * 1.1:
            return "none"

        if abs(dy) > abs(dx):
            return "up" if dy < 0 else "down"
        else:
            return "right" if dx > 0 else "left"
