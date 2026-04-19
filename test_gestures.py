"""
Terminal / visual test for gesture detection.
Opens camera, draws hand landmarks + detected gesture on screen.
Does NOT trigger any media actions — safe to run anytime.

Press Q in the window to quit.
"""

import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import time

from gesture_classifier import (
    GestureClassifier,
    GESTURE_THUMBS_UP, GESTURE_THUMBS_DOWN,
    GESTURE_THUMB_LEFT, GESTURE_THUMB_RIGHT,
    GESTURE_OPEN_PALM, GESTURE_MIDDLE_FINGER,
    GESTURE_INDEX_UP, GESTURE_PINKY_UP,
    HOLD_DURATION,
)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")

GESTURE_LABELS = {
    GESTURE_THUMBS_UP:     ("THUMBS UP",     (0, 200, 0)),
    GESTURE_THUMBS_DOWN:   ("THUMBS DOWN",   (0, 80, 255)),
    GESTURE_OPEN_PALM:     ("OPEN PALM",     (255, 180, 0)),
    GESTURE_THUMB_RIGHT:   ("THUMB RIGHT",   (200, 0, 200)),
    GESTURE_THUMB_LEFT:    ("THUMB LEFT",    (0, 200, 200)),
    GESTURE_MIDDLE_FINGER: ("MIDDLE FINGER", (0, 0, 220)),
    GESTURE_INDEX_UP:      ("INDEX UP",      (0, 220, 180)),
    GESTURE_PINKY_UP:      ("PINKY UP",      (220, 100, 0)),
}

ACTION_LABELS = {
    GESTURE_THUMBS_UP:     "-> Volume UP",
    GESTURE_THUMBS_DOWN:   "-> Volume DOWN",
    GESTURE_OPEN_PALM:     "-> Play / Pause",
    GESTURE_THUMB_RIGHT:   "-> Next Track",
    GESTURE_THUMB_LEFT:    "-> Prev Track",
    GESTURE_MIDDLE_FINGER: "-> Lock Screen",
    GESTURE_INDEX_UP:      "-> Mic Mute Toggle",
    GESTURE_PINKY_UP:      "-> Quit Waiv",
}

# Landmark connections for manual drawing (MediaPipe hand topology)
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),       # thumb
    (0,5),(5,6),(6,7),(7,8),       # index
    (0,9),(9,10),(10,11),(11,12),  # middle
    (0,13),(13,14),(14,15),(15,16),# ring
    (0,17),(17,18),(18,19),(19,20),# pinky
    (5,9),(9,13),(13,17),          # palm
]


def draw_landmarks(frame, landmarks, w, h):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 180, 80), 2)
    for x, y in pts:
        cv2.circle(frame, (x, y), 5, (255, 255, 255), -1)
        cv2.circle(frame, (x, y), 5, (0, 150, 0), 1)


def main():
    if not os.path.exists(MODEL_PATH):
        print(f"ERROR: Model not found at {MODEL_PATH}")
        print("Run: curl -L -o hand_landmarker.task "
              "https://storage.googleapis.com/mediapipe-models/"
              "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task")
        return

    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = mp_vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    detector = mp_vision.HandLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open camera.")
        print("Check: System Preferences > Privacy & Security > Camera")
        return

    classifier = GestureClassifier()
    last_confirmed = None
    last_confirmed_time = 0.0

    print("Gesture test running — press Q in the window to quit")
    print("Gestures: thumbs up/down  |  thumb left/right  |  open palm")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

        landmarks = None
        if result.hand_landmarks:
            landmarks = result.hand_landmarks[0]
            draw_landmarks(frame, landmarks, w, h)

        raw_gesture = classifier._classify_raw(landmarks) if landmarks else None
        confirmed   = classifier.update(landmarks)

        if confirmed:
            last_confirmed = confirmed
            last_confirmed_time = time.monotonic()

        show_confirmed = (
            last_confirmed
            and (time.monotonic() - last_confirmed_time) < 2.0
        )

        # --- Top bar: current detected gesture ---
        cv2.rectangle(frame, (0, 0), (w, 52), (30, 30, 30), -1)

        if raw_gesture and raw_gesture in GESTURE_LABELS:
            label, color = GESTURE_LABELS[raw_gesture]
            cv2.putText(frame, f"Detecting: {label}", (10, 36),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        else:
            cv2.putText(frame, "No gesture", (10, 36),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (100, 100, 100), 1)

        # --- Hold progress bar (fills over HOLD_DURATION seconds) ---
        if raw_gesture and landmarks:
            elapsed = time.monotonic() - classifier._candidate_since
            progress = min(1.0, elapsed / HOLD_DURATION)
            bar_w = int(w * progress)
            cv2.rectangle(frame, (0, 50), (bar_w, 57), (0, 220, 100), -1)

        # --- Bottom bar: last confirmed gesture ---
        if show_confirmed and last_confirmed in GESTURE_LABELS:
            label, color = GESTURE_LABELS[last_confirmed]
            action = ACTION_LABELS[last_confirmed]
            cv2.rectangle(frame, (0, h - 65), (w, h), (20, 20, 20), -1)
            cv2.putText(frame, f"FIRED: {label}  {action}",
                        (10, h - 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)

        cv2.imshow("Waiv Gesture Test — Q to quit", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    detector.close()


if __name__ == "__main__":
    main()
