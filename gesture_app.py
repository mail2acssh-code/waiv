"""
Waiv Gesture Control — main background loop with status bar menu.

Status bar icon lifecycle:
  ◐◓◑◒  (spinner)  — camera / model initialising
  ✋               — active, watching for gestures
  ⏸               — paused by user
  ⚠️               — camera or model error

Menu: Show Gestures… | Pause/Resume | Quit
"""

import logging
import os
import signal
import sys
import time
import threading

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import rumps
from PyObjCTools import AppHelper

from gesture_classifier import GestureClassifier
import media_controller
import media_detector
from hud import WaivHUD, OnboardingWindow, is_onboarded

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CAMERA_INDEX  = 0
ACTIVE_FPS    = 15
IDLE_SLEEP    = 2.0
ALWAYS_ACTIVE = "--always-active" in sys.argv
_HERE         = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH    = os.path.join(_HERE, "hand_landmarker.task")

_paused   = False
_stop_evt = threading.Event()

_SPINNER = ["◐", "◓", "◑", "◒"]


class WaivStatusBar(rumps.App):
    def __init__(self, hud: WaivHUD, onboarding: OnboardingWindow):
        super().__init__(_SPINNER[0], quit_button=None)
        self._hud        = hud
        self._onboarding = onboarding
        self._spinner_idx = 0

        self._pause_item = rumps.MenuItem("Pause Waiv", callback=self._toggle_pause)
        self.menu = [
            rumps.MenuItem("Show Gestures…", callback=self._show_gestures),
            None,
            self._pause_item,
            None,
            rumps.MenuItem("Quit Waiv", callback=self._quit),
        ]

        # Spin while camera/model is loading
        self._spinner_timer = rumps.Timer(self._spin, 0.18)
        self._spinner_timer.start()

    # --- spinner ---

    def _spin(self, timer):
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER)
        self.title = _SPINNER[self._spinner_idx]

    def set_ready(self):
        """Switch icon to ✋ when camera is open. Called from gesture loop."""
        self._spinner_timer.stop()
        self.title = "✋"

    def set_error(self):
        """Switch icon to ⚠️ on init failure. Called from gesture loop."""
        self._spinner_timer.stop()
        self.title = "⚠️"

    # --- menu callbacks ---

    def _show_gestures(self, sender):
        self._onboarding.show()

    def _toggle_pause(self, sender):
        global _paused
        _paused = not _paused
        if _paused:
            sender.title = "Resume Waiv"
            self.title   = "⏸"
            media_controller._notify("Waiv Paused", "Gesture detection off.")
        else:
            sender.title = "Pause Waiv"
            self.title   = "✋"
            media_controller._notify("Waiv Resumed", "Gesture detection on.")

    def _quit(self, sender):
        log.info("Quit requested from menu.")
        media_controller._notify("Waiv Stopping", "Goodbye.")
        import subprocess
        subprocess.run(
            ["launchctl", "unload",
             os.path.expanduser("~/Library/LaunchAgents/com.waiv.gesture.plist")],
            capture_output=True,
        )
        _stop_evt.set()                # signal gesture loop to release camera
        time.sleep(0.4)                # give it a moment to call cap.release()
        rumps.quit_application()


# ---------------------------------------------------------------------------
# Gesture loop (background thread)
# ---------------------------------------------------------------------------

def _gesture_loop(app: WaivStatusBar, hud: WaivHUD):
    if not os.path.exists(MODEL_PATH):
        log.error("Model not found: %s", MODEL_PATH)
        AppHelper.callAfter(app.set_error)
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

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        log.error("Cannot open camera %d — permission denied or in use.", CAMERA_INDEX)
        AppHelper.callAfter(app.set_error)
        try:
            import subprocess
            subprocess.run([
                "osascript", "-e",
                'display notification "Go to System Settings > Privacy > Camera '
                'and enable Python." with title "Waiv" subtitle "Camera permission needed"'
            ], timeout=3)
        except Exception:
            pass
        os.kill(os.getpid(), signal.SIGTERM)
        return

    log.info("Camera ready. Watching for gestures…")
    AppHelper.callAfter(app.set_ready)                    # ← spinner → ✋
    threading.Thread(target=media_controller.warmup, daemon=True).start()

    classifier     = GestureClassifier()
    frame_interval = 1.0 / ACTIVE_FPS

    while not _stop_evt.is_set():
        if _paused:
            time.sleep(0.5)
            continue

        if not ALWAYS_ACTIVE and not media_detector.is_playing():
            log.debug("No media playing — idling")
            time.sleep(IDLE_SLEEP)
            continue

        loop_start = time.monotonic()

        ret, frame = cap.read()
        if not ret:
            log.warning("Camera frame missed")
            continue

        frame = cv2.flip(frame, 1)
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result   = detector.detect(mp_image)

        landmarks = result.hand_landmarks[0] if result.hand_landmarks else None

        gesture = classifier.update(landmarks)
        if gesture:
            log.info("Gesture: %s", gesture)
            hud.show(gesture)
            threading.Thread(
                target=media_controller.execute,
                args=(gesture,),
                daemon=True,
            ).start()

        elapsed   = time.monotonic() - loop_start
        sleep_for = frame_interval - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)

    log.info("Releasing camera…")
    cap.release()
    detector.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    try:
        import setproctitle
        setproctitle.setproctitle("waiv")
    except ImportError:
        pass

    log.info("Waiv Gesture Control starting…")

    hud        = WaivHUD()
    onboarding = OnboardingWindow()
    app        = WaivStatusBar(hud, onboarding)

    threading.Thread(
        target=_gesture_loop,
        args=(app, hud),
        daemon=True,
        name="gesture-loop",
    ).start()

    # First-run: show gesture guide automatically after app settles
    if not is_onboarded():
        AppHelper.callLater(1.0, onboarding.show)

    app.run()


if __name__ == "__main__":
    run()
