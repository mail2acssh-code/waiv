"""
HUD overlay, setup wizard, and onboarding sheet for Waiv.

All AppKit objects must be created/used on the main thread.
Public methods (hud.show, wizard.on_gesture, etc.) are thread-safe.
"""

import ctypes
import os
import subprocess
import objc
from AppKit import (
    NSAnimationContext,
    NSAppearance,
    NSApplication,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSButton,
    NSBezelStyleRounded,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSImage,
    NSImageSymbolConfiguration,
    NSImageView,
    NSMakeRect,
    NSObject,
    NSScreen,
    NSTextField,
    NSTextAlignmentCenter,
    NSView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskMiniaturizable,
)
from PyObjCTools import AppHelper

_SENTINEL = os.path.expanduser("~/.config/waiv/.onboarded")
_cam_tcc_meta_registered = False


def is_onboarded() -> bool:
    return os.path.exists(_SENTINEL)


def mark_onboarded():
    os.makedirs(os.path.dirname(_SENTINEL), exist_ok=True)
    with open(_SENTINEL, "w") as f:
        f.write("1")


# ── Accessibility permission helper ───────────────────────────────────────────

_ax_lib = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_ax_lib.AXIsProcessTrusted.restype = ctypes.c_bool


def is_accessibility_trusted() -> bool:
    return bool(_ax_lib.AXIsProcessTrusted())


def open_accessibility_settings():
    subprocess.run(
        ["open",
         "x-apple.systempreferences:com.apple.preference.security"
         "?Privacy_Accessibility"],
        capture_output=True,
    )


def open_camera_settings():
    subprocess.run(
        ["open",
         "x-apple.systempreferences:com.apple.preference.security"
         "?Privacy_Camera"],
        capture_output=True,
    )


# ── Gesture → HUD info ────────────────────────────────────────────────────────

GESTURE_HUD_INFO = {
    "thumbs_up":     ("speaker.wave.3.fill",  "Volume Up"),
    "thumbs_down":   ("speaker.wave.1.fill",  "Volume Down"),
    "open_palm":     ("playpause.fill",        "Play / Pause"),
    "thumb_right":   ("forward.end.fill",      "Next Track"),
    "thumb_left":    ("backward.end.fill",     "Previous Track"),
    "middle_finger": ("lock.fill",             "Lock Screen"),
    "index_up":      ("mic.fill",              "Mic Toggle"),
    "pinky_up":      ("power",                 "Goodbye"),
}

ONBOARDING_ROWS = [
    ("speaker.wave.3.fill",  "Thumbs Up",     "Volume Up"),
    ("speaker.wave.1.fill",  "Thumbs Down",   "Volume Down"),
    ("playpause.fill",        "Open Palm",     "Play / Pause"),
    ("forward.end.fill",     "Thumb Right",   "Next Track"),
    ("backward.end.fill",    "Thumb Left",    "Previous Track"),
    ("lock.fill",            "Middle Finger", "Lock Screen"),
    ("mic.fill",             "Index Up",      "Mic Toggle"),
    ("power",                "Pinky Up",      "Quit Waiv"),
]

# ── SF Symbol helpers ─────────────────────────────────────────────────────────

def _sf_symbol(name: str, point_size: float, color: NSColor) -> NSImage:
    cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_(point_size, 0.0)
    base = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    img  = base.imageWithSymbolConfiguration_(cfg)
    # imageWithTintColor_ is macOS 12+; use a lock/unlock drawing fallback for older
    try:
        return img.imageWithTintColor_(color)
    except AttributeError:
        tinted = img.copy()
        tinted.lockFocus()
        color.set()
        from AppKit import NSRectFillUsingOperation, NSCompositingOperationSourceIn, NSZeroRect
        import AppKit
        AppKit.NSRectFillUsingOperation(AppKit.NSMakeRect(0, 0, img.size().width, img.size().height),
                                        AppKit.NSCompositingOperationSourceIn)
        tinted.unlockFocus()
        return tinted


def _image_view(frame, symbol_name: str, point_size: float, color: NSColor) -> NSImageView:
    iv = NSImageView.alloc().initWithFrame_(frame)
    iv.setImage_(_sf_symbol(symbol_name, point_size, color))
    iv.setImageScaling_(3)
    return iv


def _label(parent, text, frame, size=14, bold=False, color=None, align=NSTextAlignmentCenter):
    f = NSTextField.alloc().initWithFrame_(frame)
    f.setStringValue_(text)
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if color:
        f.setTextColor_(color)
    f.setAlignment_(align)
    f.setEditable_(False)
    f.setBordered_(False)
    f.setDrawsBackground_(False)
    if parent is not None:
        parent.addSubview_(f)
    return f


# ── Window close delegate ─────────────────────────────────────────────────────

class _WindowDelegate(NSObject):
    def init(self):
        self = objc.super(_WindowDelegate, self).init()
        if self is None:
            return None
        self._cb = None
        return self

    def windowWillClose_(self, notification):
        if self._cb:
            self._cb()


# ── NSObject action target ────────────────────────────────────────────────────

class _ButtonTarget(NSObject):
    def init(self):
        self = objc.super(_ButtonTarget, self).init()
        if self is None:
            return None
        self._cb = None
        return self

    def doAction_(self, sender):
        if self._cb:
            self._cb()


# ── HUD overlay ───────────────────────────────────────────────────────────────

class WaivHUD:
    SZ       = 160
    RADIUS   = 22
    Y_OFFSET = 60

    def __init__(self):
        self._window      = None
        self._icon_view   = None
        self._label_field = None
        self._dismiss_gen = 0

    def show(self, gesture: str):
        AppHelper.callAfter(self._show_main, gesture)

    def _show_main(self, gesture):
        if gesture not in GESTURE_HUD_INFO:
            return
        symbol_name, label = GESTURE_HUD_INFO[gesture]

        if self._window is None:
            self._build()

        self._icon_view.setImage_(_sf_symbol(symbol_name, 52, NSColor.whiteColor()))
        self._label_field.setStringValue_(label)

        screen = NSScreen.mainScreen().frame()
        x = screen.origin.x + (screen.size.width - self.SZ) / 2
        y = screen.origin.y + self.Y_OFFSET
        self._window.setFrame_display_(NSMakeRect(x, y, self.SZ, self.SZ), False)

        self._dismiss_gen += 1
        gen = self._dismiss_gen

        self._window.setAlphaValue_(0.0)
        self._window.orderFrontRegardless()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.15)
        self._window.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

        AppHelper.callLater(1.8, lambda: self._begin_dismiss(gen))

    def _begin_dismiss(self, gen):
        if gen != self._dismiss_gen or self._window is None:
            return
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.25)
        self._window.animator().setAlphaValue_(0.0)
        NSAnimationContext.endGrouping()
        AppHelper.callLater(0.26, self._hide)

    def _hide(self):
        if self._window:
            self._window.orderOut_(None)

    def _build(self):
        SZ = self.SZ
        rect = NSMakeRect(0, 0, SZ, SZ)

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
        )
        win.setLevel_(NSFloatingWindowLevel + 2)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(True)

        effect = NSVisualEffectView.alloc().initWithFrame_(rect)
        effect.setMaterial_(22)
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        win.setContentView_(effect)

        effect.setWantsLayer_(True)
        layer = effect.layer()
        layer.setCornerRadius_(self.RADIUS)
        layer.setMasksToBounds_(True)
        layer.setCornerCurve_("continuous")

        icon_sz = 72
        icon_x  = (SZ - icon_sz) / 2
        icon_y  = SZ - icon_sz - 12
        iv = _image_view(NSMakeRect(icon_x, icon_y, icon_sz, icon_sz),
                         "speaker.wave.3.fill", 52, NSColor.whiteColor())
        effect.addSubview_(iv)
        self._icon_view = iv

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(8, 12, SZ - 16, 46))
        lbl.setFont_(NSFont.boldSystemFontOfSize_(14))
        lbl.setTextColor_(NSColor.whiteColor())
        lbl.setAlignment_(NSTextAlignmentCenter)
        lbl.setEditable_(False)
        lbl.setBordered_(False)
        lbl.setDrawsBackground_(False)
        effect.addSubview_(lbl)
        self._label_field = lbl

        self._window = win


# ── Setup Wizard ──────────────────────────────────────────────────────────────

# (symbol, step_title, pending_detail, active_detail, done_detail)
_WIZARD_STEPS = [
    ("hand.point.up.left.fill",
     "Accessibility",
     "Waiting…",
     "Click 'Open Accessibility Settings', add Waiv, then return here.",
     "Accessibility granted"),
    ("camera.fill",
     "Camera Access",
     "Waiting…",
     "Allow camera access when prompted by macOS.",
     "Camera access confirmed"),
    ("hand.raised.fill",
     "Gesture Test",
     "Waiting…",
     "Show thumbs up toward the camera to confirm.",
     "Gesture detected — volume up!"),
    ("checkmark.seal.fill",
     "All Set",
     "",
     "Waiv is ready — enjoy!",
     "Waiv is ready — enjoy!"),
]

# Step indices
_STEP_ACCESSIBILITY = 0
_STEP_CAMERA        = 1
_STEP_GESTURE       = 2
_STEP_DONE          = 3

# Step states
_PENDING = 0
_ACTIVE  = 1
_DONE    = 2


class SetupWizardWindow:
    """
    Four-step setup wizard shown on first launch (and re-openable from menu).
      Step 0 — Accessibility permission  (polls AXIsProcessTrusted)
      Step 1 — Camera access             (auto-advances when camera opens)
      Step 2 — Gesture test              (user raises open palm)
      Step 3 — All Set

    Thread-safe: camera_ready() and on_gesture() may be called from any thread.
    """

    W, H = 500, 510

    def __init__(self):
        self._window            = None
        self._content           = None
        self._step_rows         = []
        self._big_icon          = None
        self._instruction       = None
        self._done_btn          = None
        self._settings_btn      = None
        self._btn_target        = None
        self._settings_target   = None
        self._current           = -1
        self._on_complete       = None
        self._camera_ready      = False
        self._camera_granted    = False   # set once camera TCC confirmed in wizard
        self._palm_armed        = False
        self._ax_timer          = None   # rumps.Timer polling accessibility
        self._cam_timer         = None
        self._cam_timer_ticks   = 0
        self._back_btn          = None
        self._back_target       = None
        self._win_delegate      = None

    # ── public / thread-safe ──────────────────────────────────────────────────

    def show(self, on_complete=None):
        self._on_complete = on_complete
        AppHelper.callAfter(self._show_main)

    def show_health_check(self):
        """
        Show wizard in health-check mode: immediately verify all permissions
        and display current status. Called from 'Show Setup…' menu item.
        """
        self._on_complete = None
        AppHelper.callAfter(self._show_health_check_main)

    def _show_health_check_main(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if self._window and self._window.isVisible():
            self._window.makeKeyAndOrderFront_(None)
            # Re-run the check even if already visible
        else:
            self._build()
            self._window.center()
            self._window.makeKeyAndOrderFront_(None)

        # Show all steps as PENDING first, then check each
        for i in range(len(_WIZARD_STEPS)):
            self._set_row_state(i, _PENDING)

        # Step 0 — Accessibility
        if is_accessibility_trusted():
            self._set_row_state(_STEP_ACCESSIBILITY, _DONE)
        else:
            self._set_row_state(_STEP_ACCESSIBILITY, _ACTIVE)
            self._settings_btn.setHidden_(False)

        # Step 1 — Camera
        try:
            import gesture_app as _ga
            cam_ok = _ga._camera_ok
        except Exception:
            cam_ok = False
        if cam_ok:
            self._set_row_state(_STEP_CAMERA, _DONE)
        else:
            self._set_row_state(_STEP_CAMERA, _ACTIVE)
            self._settings_btn.setTitle_("Open Camera Settings…")
            self._settings_target._cb = self._open_camera_settings
            self._settings_btn.setHidden_(False)

        # Step 2 — Gesture (mark done if camera running)
        if cam_ok:
            self._set_row_state(_STEP_GESTURE, _DONE)
        else:
            self._set_row_state(_STEP_GESTURE, _PENDING)

        # Step 3 — All Set
        ax_ok = is_accessibility_trusted()
        if ax_ok and cam_ok:
            self._set_row_state(_STEP_DONE, _DONE)
            self._big_icon.setImage_(_sf_symbol(
                _WIZARD_STEPS[_STEP_DONE][0], 64, NSColor.systemGreenColor()))
            self._instruction.setStringValue_("All permissions are in place.")
        else:
            self._big_icon.setImage_(_sf_symbol(
                "exclamationmark.triangle.fill", 64, NSColor.systemOrangeColor()))
            issues = []
            if not ax_ok:
                issues.append("Accessibility not granted")
            if not cam_ok:
                issues.append("Camera unavailable")
            self._instruction.setStringValue_("\n".join(issues))

        self._done_btn.setHidden_(True)
        self._current = -1  # not in sequential flow

    def camera_ready(self):
        """Called from gesture thread when camera opens."""
        self._camera_ready = True
        if self._current == _STEP_CAMERA:
            AppHelper.callAfter(self._complete_step, _STEP_CAMERA)
        elif self._current == _STEP_GESTURE and self._settings_btn.isHidden():
            # Only arm if user already pressed Start Camera
            AppHelper.callAfter(self._arm_gesture_detection)

    def camera_error(self):
        """Called from gesture thread if camera fails."""
        AppHelper.callAfter(self._mark_camera_error)

    def on_gesture(self, gesture: str):
        if self._palm_armed and gesture == "thumbs_up":
            self._palm_armed = False
            import threading as _t
            import media_controller as _mc
            _t.Thread(target=_mc.volume_up, daemon=True).start()
            AppHelper.callAfter(self._complete_step, _STEP_GESTURE)

    def _on_start_camera_pressed(self):
        self._settings_btn.setHidden_(True)
        self._instruction.setStringValue_("Camera starting…")
        self._trigger_system_events_permission()
        try:
            import gesture_app as _ga
            _ga._camera_permitted.set()   # ensure gesture loop unblocks (fallback)
        except Exception:
            pass
        if self._camera_ready:
            self._arm_gesture_detection()

    def _arm_gesture_detection(self):
        """Enable thumbs-up detection and update instruction. Main thread only."""
        if self._current != _STEP_GESTURE:
            return
        self._palm_armed = True
        gray2 = NSColor.colorWithRed_green_blue_alpha_(0.6, 0.6, 0.6, 1.0)
        self._instruction.setTextColor_(gray2)
        self._instruction.setStringValue_(
            "Show thumbs up toward the camera.\n"
            "This also grants media control permission."
        )

    # ── main-thread internals ─────────────────────────────────────────────────

    def _show_main(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if self._window and self._window.isVisible():
            self._window.makeKeyAndOrderFront_(None)
            return
        self._build()
        self._window.center()
        self._window.makeKeyAndOrderFront_(None)
        self._go_to_step(_STEP_ACCESSIBILITY)

    def _go_to_step(self, idx):
        if idx >= len(_WIZARD_STEPS):
            return
        self._current = idx
        self._stop_cam_timer()
        sym, _, _, active_detail, _ = _WIZARD_STEPS[idx]

        for i in range(len(_WIZARD_STEPS)):
            if i < idx:
                self._set_row_state(i, _DONE)
            elif i == idx:
                self._set_row_state(i, _ACTIVE)
            else:
                self._set_row_state(i, _PENDING)

        colour = NSColor.systemGreenColor() if idx == _STEP_DONE else NSColor.whiteColor()
        self._big_icon.setImage_(_sf_symbol(sym, 64, colour))
        gray2 = NSColor.colorWithRed_green_blue_alpha_(0.6, 0.6, 0.6, 1.0)
        self._instruction.setTextColor_(gray2)
        self._instruction.setStringValue_(active_detail)

        self._done_btn.setHidden_(True)
        self._settings_btn.setHidden_(True)
        self._back_btn.setHidden_(idx not in (_STEP_CAMERA,))

        if idx == _STEP_ACCESSIBILITY:
            self._settings_btn.setTitle_("Open Accessibility Settings…")
            self._settings_target._cb = self._open_settings
            if is_accessibility_trusted():
                AppHelper.callLater(0.4, lambda: self._complete_step(_STEP_ACCESSIBILITY))
            else:
                self._settings_btn.setHidden_(False)
                self._start_ax_poll()

        elif idx == _STEP_CAMERA:
            self._stop_ax_poll()
            self._settings_btn.setTitle_("Open Camera Settings…")
            self._settings_target._cb = self._open_camera_settings
            self._settings_btn.setHidden_(False)
            self._start_cam_permission_request()

        elif idx == _STEP_GESTURE:
            self._settings_btn.setTitle_("Start Camera")
            self._settings_target._cb = self._on_start_camera_pressed
            self._settings_btn.setHidden_(False)

        elif idx == _STEP_DONE:
            self._set_row_state(_STEP_DONE, _DONE)
            self._done_btn.setHidden_(False)
            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.4)
            self._big_icon.animator().setAlphaValue_(0.0)
            NSAnimationContext.endGrouping()
            AppHelper.callLater(0.4, self._pulse_done)

    def _pulse_done(self):
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.4)
        self._big_icon.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

    def _complete_step(self, idx):
        if idx != self._current:
            return
        self._set_row_state(idx, _DONE)
        _, _, _, _, done_detail = _WIZARD_STEPS[idx]
        self._instruction.setTextColor_(
            NSColor.colorWithRed_green_blue_alpha_(0.6, 0.6, 0.6, 1.0))
        self._instruction.setStringValue_(done_detail)
        AppHelper.callLater(0.6, lambda: self._go_to_step(idx + 1))

    def _mark_camera_error(self):
        if self._current != _STEP_CAMERA:
            return
        self._stop_cam_timer()
        self._instruction.setStringValue_(
            "Camera access denied.\n"
            "Open Camera Settings, allow Waiv, then return here."
        )
        self._big_icon.setImage_(_sf_symbol("exclamationmark.triangle.fill", 72,
                                            NSColor.systemOrangeColor()))

    def _set_row_state(self, idx, state):
        _, iv, title_f, detail_f = self._step_rows[idx]
        sym_name, step_title, pending_d, active_d, done_d = _WIZARD_STEPS[idx]

        gray3 = NSColor.colorWithRed_green_blue_alpha_(0.35, 0.35, 0.35, 1.0)
        gray2 = NSColor.colorWithRed_green_blue_alpha_(0.6,  0.6,  0.6,  1.0)

        if state == _PENDING:
            iv.setImage_(_sf_symbol("circle", 18, gray3))
            title_f.setTextColor_(gray3)
            detail_f.setTextColor_(gray3)
            detail_f.setStringValue_(pending_d)
        elif state == _ACTIVE:
            iv.setImage_(_sf_symbol("circle.dotted", 18, NSColor.systemBlueColor()))
            title_f.setTextColor_(NSColor.whiteColor())
            detail_f.setTextColor_(gray2)
            detail_f.setStringValue_(active_d)
        else:
            iv.setImage_(_sf_symbol("checkmark.circle.fill", 18, NSColor.systemGreenColor()))
            title_f.setTextColor_(NSColor.whiteColor())
            detail_f.setTextColor_(gray2)
            detail_f.setStringValue_(done_d)

        self._step_rows[idx] = (state, iv, title_f, detail_f)

    def _start_ax_poll(self):
        """Poll every 1.5 s until Accessibility is granted."""
        if self._ax_timer:
            return
        import rumps
        self._ax_timer = rumps.Timer(self._check_ax, 1.5)
        self._ax_timer.start()

    def _stop_ax_poll(self):
        if self._ax_timer:
            self._ax_timer.stop()
            self._ax_timer = None

    def _check_ax(self, _timer):
        if self._current != _STEP_ACCESSIBILITY:
            self._stop_ax_poll()
            return
        if is_accessibility_trusted():
            self._stop_ax_poll()
            AppHelper.callAfter(self._complete_step, _STEP_ACCESSIBILITY)

    def _start_cam_permission_request(self):
        """Trigger camera TCC dialog from main thread via AVCaptureDevice."""
        AppHelper.callAfter(self._request_cam_tcc_main)

    def _request_cam_tcc_main(self):
        """Main thread. Use AVCaptureDevice to check/request camera TCC."""
        global _cam_tcc_meta_registered
        try:
            import ctypes as _ct
            _ct.CDLL('/System/Library/Frameworks/AVFoundation.framework/AVFoundation')
            import objc as _objc

            if not _cam_tcc_meta_registered:
                _objc.registerMetaDataForSelector(
                    b"AVCaptureDevice",
                    b"requestAccessForMediaType:completionHandler:",
                    {
                        "arguments": {
                            3: {
                                "callable": {
                                    "retval": {"type": b"v"},
                                    "arguments": {
                                        0: {"type": b"@"},
                                        1: {"type": b"c"},
                                    },
                                }
                            }
                        }
                    },
                )
                _cam_tcc_meta_registered = True

            AVCapDev = _objc.lookUpClass('AVCaptureDevice')
            status = int(AVCapDev.authorizationStatusForMediaType_("vide"))

            if status == 3:
                self._on_camera_access_confirmed()
                return
            if status == 2:
                self._instruction.setStringValue_(
                    "Camera access denied.\n"
                    "Open Camera Settings to allow Waiv, then return here."
                )
                self._start_cam_cv2_poll()
                return
            # 0=notDetermined: show system dialog
            def _handler(granted):
                if granted:
                    AppHelper.callAfter(self._on_camera_access_confirmed)
                else:
                    AppHelper.callAfter(lambda: self._instruction.setStringValue_(
                        "Camera access denied.\n"
                        "Open Camera Settings to allow Waiv."
                    ))
            AVCapDev.requestAccessForMediaType_completionHandler_("vide", _handler)
        except Exception as exc:
            import logging
            logging.getLogger('hud').warning("Camera TCC ObjC: %s", exc)
            self._start_cam_cv2_poll()

    def _start_cam_cv2_poll(self):
        """Fallback: poll cv2 to detect when camera TCC is granted via System Settings."""
        import threading as _t
        self._camera_granted = False

        def _poll():
            import time
            while not self._camera_granted and self._current == _STEP_CAMERA:
                try:
                    import cv2
                    cap = cv2.VideoCapture(0)
                    if cap.isOpened():
                        cap.release()
                        AppHelper.callAfter(self._on_camera_access_confirmed)
                        return
                    cap.release()
                except Exception:
                    pass
                time.sleep(2.0)

        _t.Thread(target=_poll, daemon=True, name="cam-permit").start()

    def _on_camera_access_confirmed(self):
        if self._camera_granted or self._current != _STEP_CAMERA:
            return
        self._camera_granted = True
        try:
            import gesture_app as _ga
            _ga._camera_permitted.set()
        except Exception:
            pass
        self._complete_step(_STEP_CAMERA)

    def _stop_cam_timer(self):
        pass  # kept for backward compat (camera_ready path)

    def _open_camera_settings(self):
        open_camera_settings()
        # polling thread continues automatically

    def _trigger_system_events_permission(self):
        """Pre-trigger Automation permission for System Events so it doesn't appear mid-use."""
        import threading as _threading
        def _run():
            try:
                import subprocess as _sp
                _sp.run(
                    ["osascript", "-e",
                     'tell application "System Events" to return true'],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass
        _threading.Thread(target=_run, daemon=True, name="sysevt-perm").start()

    def _go_back(self):
        self._stop_cam_timer()
        self._stop_ax_poll()
        self._palm_armed = False
        if self._current > 0:
            self._go_to_step(self._current - 1)

    def _open_settings(self):
        open_accessibility_settings()

    def _on_window_closed(self):
        """User dismissed wizard via X — unblock the gesture loop so app runs."""
        self._stop_ax_poll()
        self._stop_cam_timer()
        self._palm_armed = False
        self._camera_granted = True   # stop background poll thread
        try:
            import gesture_app as _ga
            _ga._camera_permitted.set()
            _ga._setup_done.set()
        except Exception:
            pass
        mark_onboarded()
        if self._on_complete:
            self._on_complete()

    def _finish(self):
        mark_onboarded()
        if self._on_complete:
            self._on_complete()
        if self._window:
            self._window.orderOut_(None)

    # ── builder ───────────────────────────────────────────────────────────────

    def _build(self):
        W, H = self.W, self.H

        # ── Window — forced dark, flat black like the landing page ────────────
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False,
        )
        win.setTitle_("Setting up Waiv")
        win.setLevel_(NSFloatingWindowLevel + 1)
        delegate = _WindowDelegate.alloc().init()
        delegate._cb = self._on_window_closed
        self._win_delegate = delegate
        win.setDelegate_(delegate)
        win.setTitlebarAppearsTransparent_(True)
        win.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
        # Flat opaque dark surface (matches landing page #0d0d0d)
        win.setBackgroundColor_(
            NSColor.colorWithRed_green_blue_alpha_(0.05, 0.05, 0.05, 1.0)
        )

        bg = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        win.setContentView_(bg)
        self._content = bg

        # Colors matching landing page dark theme
        white   = NSColor.whiteColor()
        gray2   = NSColor.colorWithRed_green_blue_alpha_(0.6, 0.6, 0.6, 1.0)   # #999
        gray3   = NSColor.colorWithRed_green_blue_alpha_(0.35, 0.35, 0.35, 1.0) # #555
        border  = NSColor.colorWithRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.1)
        green   = NSColor.systemGreenColor()
        blue    = NSColor.systemBlueColor()

        def _div(parent, x, y, w, h=1):
            d = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
            d.setEditable_(False); d.setBordered_(False)
            d.setDrawsBackground_(True)
            d.setBackgroundColor_(border)
            parent.addSubview_(d)

        # ── Header ────────────────────────────────────────────────────────────
        _label(bg, "Setting up Waiv",
               NSMakeRect(24, H - 54, W - 48, 28),
               size=18, bold=True, color=white)
        _label(bg, "Confirming all permissions are in place.",
               NSMakeRect(24, H - 76, W - 48, 20),
               size=12, color=gray2)
        _div(bg, 0, H - 86, W)

        # ── Step rows — landing page install-step style ───────────────────────
        ROW_H = 56
        y = H - 88
        self._step_rows = []
        for i, (sym, step_title, pending_d, active_d, done_d) in enumerate(_WIZARD_STEPS):
            row_y = y - ROW_H

            # Step state icon (SF symbol)
            iv = _image_view(NSMakeRect(20, row_y + 17, 22, 22),
                             "circle", 18, gray3)
            bg.addSubview_(iv)

            # Step title
            title_f = _label(bg, step_title,
                             NSMakeRect(52, row_y + 20, W - 80, 18),
                             size=13, bold=True, color=gray3)
            title_f.setAlignment_(4)

            # Step detail
            detail_f = _label(bg, pending_d,
                              NSMakeRect(52, row_y + 4, W - 80, 16),
                              size=11, color=gray3)
            detail_f.setAlignment_(4)

            self._step_rows.append((_PENDING, iv, title_f, detail_f))

            # Thin divider between rows (not after last)
            if i < len(_WIZARD_STEPS) - 1:
                _div(bg, 52, row_y, W - 52)

            y = row_y

        # ── Divider below steps ───────────────────────────────────────────────
        sep_y = y
        _div(bg, 0, sep_y, W)

        # ── Big centre icon ───────────────────────────────────────────────────
        icon_area_h = sep_y - 68   # 68 = button bar height
        icon_y = 68 + (icon_area_h - 80) // 2
        self._big_icon = _image_view(
            NSMakeRect((W - 80) // 2, icon_y, 80, 80),
            "hand.point.up.left.fill", 64, white
        )
        bg.addSubview_(self._big_icon)

        # ── Instruction label ─────────────────────────────────────────────────
        inst_y = icon_y - 52
        self._instruction = _label(
            bg, "",
            NSMakeRect(24, inst_y, W - 48, 46),
            size=13, color=gray2
        )
        self._instruction.setMaximumNumberOfLines_(3)
        self._instruction.setLineBreakMode_(3)
        self._instruction.setAlignment_(1)  # centre

        # ── Button bar ────────────────────────────────────────────────────────
        _div(bg, 0, 60, W)

        # Back button — left side, hidden on first/last step
        back_btn = NSButton.alloc().initWithFrame_(NSMakeRect(20, 16, 80, 32))
        back_btn.setTitle_("← Back")
        back_btn.setBezelStyle_(NSBezelStyleRounded)
        back_btn.setHidden_(True)

        back_target = _ButtonTarget.alloc().init()
        back_target._cb = self._go_back
        self._back_target = back_target
        back_btn.setTarget_(back_target)
        back_btn.setAction_("doAction:")
        bg.addSubview_(back_btn)
        self._back_btn = back_btn

        # "Open Camera Settings…" and "Continue →" — side by side for camera step
        sbtn = NSButton.alloc().initWithFrame_(NSMakeRect(W // 2 - 170, 16, 160, 32))
        sbtn.setTitle_("Open Settings…")
        sbtn.setBezelStyle_(NSBezelStyleRounded)
        sbtn.setHidden_(True)

        s_target = _ButtonTarget.alloc().init()
        s_target._cb = self._open_settings
        self._settings_target = s_target
        sbtn.setTarget_(s_target)
        sbtn.setAction_("doAction:")
        bg.addSubview_(sbtn)
        self._settings_btn = sbtn

        # "Start Using Waiv" — primary, shown on done step
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(W // 2 - 82, 16, 164, 32))
        btn.setTitle_("Start Using Waiv")
        btn.setBezelStyle_(NSBezelStyleRounded)
        btn.setHidden_(True)

        target = _ButtonTarget.alloc().init()
        target._cb = self._finish
        self._btn_target = target
        btn.setTarget_(target)
        btn.setAction_("doAction:")
        bg.addSubview_(btn)
        self._done_btn = btn

        self._window = win


# ── Gesture reference sheet ───────────────────────────────────────────────────

class OnboardingWindow:
    """Gesture reference sheet shown from the menu. Thread-safe."""

    def __init__(self):
        self._window     = None
        self._btn_target = None

    def show(self):
        AppHelper.callAfter(self._show_main)

    def _show_main(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if self._window and self._window.isVisible():
            self._window.makeKeyAndOrderFront_(None)
            return
        self._build()
        self._window.center()
        self._window.makeKeyAndOrderFront_(None)

    def _build(self):
        W, H = 420, 530

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False,
        )
        win.setTitle_("Waiv — Gesture Guide")
        win.setLevel_(NSFloatingWindowLevel)
        win.setTitlebarAppearsTransparent_(True)

        effect = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        effect.setMaterial_(18)
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        win.setContentView_(effect)

        _label(effect, "Waiv Gesture Control",
               NSMakeRect(20, H - 62, W - 40, 36), size=18, bold=True)
        _label(effect, "Hold any gesture steady for 2 seconds to trigger it.",
               NSMakeRect(20, H - 90, W - 40, 26),
               size=12, color=NSColor.secondaryLabelColor())

        div = NSTextField.alloc().initWithFrame_(NSMakeRect(20, H - 100, W - 40, 1))
        div.setEditable_(False); div.setBordered_(False)
        div.setDrawsBackground_(True)
        div.setBackgroundColor_(NSColor.separatorColor())
        effect.addSubview_(div)

        ROW_H = 46
        y = H - 112
        for symbol, name, action in ONBOARDING_ROWS:
            iv = _image_view(NSMakeRect(16, y + 4, 32, 32),
                             symbol, 20, NSColor.labelColor())
            effect.addSubview_(iv)
            _label(effect, name,   NSMakeRect(58, y + 14, 160, 22),
                   size=14, bold=True, align=4)
            _label(effect, action, NSMakeRect(228, y + 14, W - 250, 22),
                   size=13, color=NSColor.secondaryLabelColor(), align=4)
            y -= ROW_H

        btn = NSButton.alloc().initWithFrame_(NSMakeRect(W // 2 - 55, 18, 110, 32))
        btn.setTitle_("Got it")
        btn.setBezelStyle_(NSBezelStyleRounded)

        target = _ButtonTarget.alloc().init()
        target._cb = lambda: win.orderOut_(None)
        self._btn_target = target
        btn.setTarget_(target)
        btn.setAction_("doAction:")
        effect.addSubview_(btn)

        self._window = win
