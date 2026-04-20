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
import shutil
import signal
import subprocess
import sys
import time
import threading

# ── Force the process into GUI/accessory mode BEFORE importing rumps ──────────
# When launched via a LaunchAgent the process has no Info.plist and macOS
# defaults it to NSApplicationActivationPolicyProhibited, which prevents the
# status-bar item from appearing.  Setting the policy here, before rumps
# touches NSApplication, ensures the item is always visible.
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory as _ACCESSORY
_ns_app = NSApplication.sharedApplication()
_ns_app.setActivationPolicy_(_ACCESSORY)

import os
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import rumps
from PyObjCTools import AppHelper

from gesture_classifier import GestureClassifier
import media_controller
import media_detector
from hud import WaivHUD, SetupWizardWindow, OnboardingWindow, is_onboarded

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

_paused            = False
_stop_evt          = threading.Event()
_camera_permitted  = threading.Event()  # set when camera permission granted in wizard
_setup_done        = threading.Event()  # set when wizard fully completes (or immediately if onboarded)
_camera_ok         = False              # True once camera successfully opens

# Wizard hooks — set while the setup wizard is active so gestures route there
_wizard: SetupWizardWindow | None = None

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
            rumps.MenuItem("Show Setup…",    callback=self._show_setup),
            None,
            self._pause_item,
            None,
            rumps.MenuItem("Uninstall Waiv", callback=self._uninstall),
            None,
            rumps.MenuItem("Quit Waiv", callback=self._quit),
        ]

        self._spinner_timer = rumps.Timer(self._spin, 0.18)
        self._spinner_timer.start()

    def _spin(self, timer):
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER)
        self.title = _SPINNER[self._spinner_idx]

    def set_ready(self):
        self._spinner_timer.stop()
        self.title = "✋"

    def set_error(self):
        self._spinner_timer.stop()
        self.title = "⚠️"

    def set_warning(self, message: str = ""):
        self._spinner_timer.stop()
        self.title = "⚠️"
        if message:
            media_controller._notify("Waiv Warning", message)

    def _show_gestures(self, sender):
        self._onboarding.show()

    def _show_setup(self, sender):
        from hud import SetupWizardWindow
        win = SetupWizardWindow()
        win.show_health_check()

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

    def _uninstall(self, sender):
        from AppKit import NSAlert
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Uninstall Waiv?")
        alert.setInformativeText_(
            "This will stop the background agent and remove all Waiv data. "
            "Drag Waiv.app to Trash afterward to complete removal."
        )
        alert.addButtonWithTitle_("Uninstall")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != 1000:
            return

        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.waiv.gesture.plist")
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        time.sleep(0.3)
        try:
            os.remove(plist_path)
        except FileNotFoundError:
            pass

        config_dir = os.path.expanduser("~/.config/waiv")
        if os.path.exists(config_dir):
            shutil.rmtree(config_dir)
        for f in ["/tmp/waiv.log", "/tmp/waiv-error.log"]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass

        subprocess.run(["tccutil", "reset", "Camera", "com.waiv.gesture"],
                       capture_output=True)

        media_controller._notify("Waiv Removed",
                                 "Drag Waiv.app to Trash to finish removal.")
        _stop_evt.set()
        time.sleep(0.4)
        rumps.quit_application()

    def _quit(self, sender):
        log.info("Quit requested from menu.")
        media_controller._notify("Waiv Stopping", "Goodbye.")
        subprocess.run(
            ["launchctl", "unload",
             os.path.expanduser("~/Library/LaunchAgents/com.waiv.gesture.plist")],
            capture_output=True,
        )
        _stop_evt.set()
        time.sleep(0.4)
        rumps.quit_application()


# ── Gesture loop ──────────────────────────────────────────────────────────────

def _gesture_loop(app: WaivStatusBar, hud: WaivHUD):
    global _wizard, _camera_ok

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

    # ── Wait for camera permission granted in wizard ──────────────────────
    log.info("Waiting for camera permission…")
    _camera_permitted.wait()
    if _stop_evt.is_set():
        return
    time.sleep(1.0)   # brief pause after wizard releases camera

    # ── Camera open with retry ─────────────────────────────────────────────
    cap = None
    while not _stop_evt.is_set():
        cap = cv2.VideoCapture(CAMERA_INDEX)
        if cap.isOpened():
            break
        cap.release()
        cap = None
        log.warning("Camera unavailable — retrying in 2 s")
        AppHelper.callAfter(app.set_error)
        if _wizard:
            _wizard.camera_error()
        _stop_evt.wait(2)

    if cap is None or _stop_evt.is_set():
        return

    log.info("Camera ready. Watching for gestures…")
    _camera_ok = True
    AppHelper.callAfter(app.set_ready)
    if _wizard:
        _wizard.camera_ready()

    threading.Thread(target=media_controller.warmup, daemon=True).start()

    classifier      = GestureClassifier()
    frame_interval  = 1.0 / ACTIVE_FPS
    ax_check_t      = time.monotonic()
    AX_CHECK_EVERY  = 60.0   # seconds

    while not _stop_evt.is_set():
        # ── Accessibility health check ─────────────────────────────────────
        now = time.monotonic()
        if now - ax_check_t > AX_CHECK_EVERY:
            ax_check_t = now
            from hud import is_accessibility_trusted
            if not is_accessibility_trusted():
                log.warning("Accessibility permission lost")
                AppHelper.callAfter(app.set_warning, "Accessibility permission lost — open Show Setup…")

        if _paused:
            time.sleep(0.5)
            continue

        if not ALWAYS_ACTIVE and not _wizard and not media_detector.is_playing():
            log.debug("No media playing — idling")
            time.sleep(IDLE_SLEEP)
            continue

        loop_start = time.monotonic()

        ret, frame = cap.read()
        if not ret:
            # Camera disconnected mid-session — retry
            log.warning("Camera lost mid-session — retrying in 5 s")
            cap.release()
            _camera_ok = False
            AppHelper.callAfter(app.set_error)
            _stop_evt.wait(5)
            cap = cv2.VideoCapture(CAMERA_INDEX)
            if not cap.isOpened():
                cap.release()
                cap = None
                break
            _camera_ok = True
            AppHelper.callAfter(app.set_ready)
            continue

        frame = cv2.flip(frame, 1)
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result   = detector.detect(mp_image)

        landmarks = result.hand_landmarks[0] if result.hand_landmarks else None
        gesture   = classifier.update(landmarks)

        if gesture:
            log.info("Gesture: %s", gesture)
            if _wizard:
                _wizard.on_gesture(gesture)
            else:
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
    if cap:
        cap.release()
    detector.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    global _wizard

    # When launched as __main__ (script or runpy), ensure 'import gesture_app'
    # returns this module so hud.py callbacks access the real running globals.
    import sys as _sys
    _sys.modules['gesture_app'] = _sys.modules['__main__']

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

    if not is_onboarded():
        wizard = SetupWizardWindow()
        _wizard = wizard

        def _wizard_done():
            global _wizard
            _wizard = None
            _setup_done.set()   # camera loop may now open the camera

        AppHelper.callLater(0.8, lambda: wizard.show(on_complete=_wizard_done))
    else:
        _camera_permitted.set()  # already onboarded — start camera immediately
        _setup_done.set()

    app.run()


if __name__ == "__main__":
    run()
