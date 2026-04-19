"""
HUD overlay (bottom-centre frosted glass) and onboarding window for Waiv.

All AppKit objects must be created and used on the main thread.
hud.show(gesture) and onboarding.show() are thread-safe — they dispatch
to the main thread via AppHelper.callAfter.
"""

import os

import objc
from AppKit import (
    NSAnimationContext,
    NSBackingStoreBuffered,
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
)
from PyObjCTools import AppHelper

# -------------------------------------------------------------------
# Sentinel file
# -------------------------------------------------------------------
_SENTINEL = os.path.expanduser("~/.config/waiv/.onboarded")


def is_onboarded() -> bool:
    return os.path.exists(_SENTINEL)


def mark_onboarded():
    os.makedirs(os.path.dirname(_SENTINEL), exist_ok=True)
    with open(_SENTINEL, "w") as f:
        f.write("1")


# -------------------------------------------------------------------
# HUD content — SF Symbol name + label per gesture
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _sf_symbol(name: str, point_size: float, color: NSColor) -> NSImage:
    """Return a tinted SF Symbol image at the requested point size."""
    cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
        point_size, 0.0  # 0.0 = regular weight
    )
    base = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    img  = base.imageWithSymbolConfiguration_(cfg)
    return img.imageWithTintColor_(color)


def _image_view(frame, symbol_name: str, point_size: float, color: NSColor) -> NSImageView:
    iv = NSImageView.alloc().initWithFrame_(frame)
    iv.setImage_(_sf_symbol(symbol_name, point_size, color))
    iv.setImageScaling_(3)  # NSImageScalingProportionallyUpOrDown
    return iv


# -------------------------------------------------------------------
# NSObject target for button actions
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# HUD
# -------------------------------------------------------------------
class WaivHUD:
    """
    Square frosted-glass HUD at the bottom-centre of the screen.
    Fades in on gesture confirmation, auto-dismisses after ~2 s.
    """

    SZ = 160          # tile size (points)
    RADIUS = 22       # corner radius
    Y_OFFSET = 60     # points above Dock

    def __init__(self):
        self._window      = None
        self._icon_view   = None
        self._label_field = None
        self._dismiss_gen = 0

    # --- public (thread-safe) ---

    def show(self, gesture: str):
        AppHelper.callAfter(self._show_main, gesture)

    # --- main-thread only ---

    def _show_main(self, gesture):
        if gesture not in GESTURE_HUD_INFO:
            return
        symbol_name, label = GESTURE_HUD_INFO[gesture]

        if self._window is None:
            self._build()

        # Swap icon
        self._icon_view.setImage_(
            _sf_symbol(symbol_name, 52, NSColor.whiteColor())
        )
        self._label_field.setStringValue_(label)

        # Centre horizontally on whichever screen has the menu bar
        screen = NSScreen.mainScreen().frame()
        x = screen.origin.x + (screen.size.width - self.SZ) / 2
        y = screen.origin.y + self.Y_OFFSET
        self._window.setFrame_display_(NSMakeRect(x, y, self.SZ, self.SZ), False)

        # Cancel any pending dismiss
        self._dismiss_gen += 1
        gen = self._dismiss_gen

        # Fade in
        self._window.setAlphaValue_(0.0)
        self._window.orderFrontRegardless()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.15)
        self._window.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

        AppHelper.callAfter(1.8, lambda: self._begin_dismiss(gen))

    def _begin_dismiss(self, gen):
        if gen != self._dismiss_gen or self._window is None:
            return
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.25)
        self._window.animator().setAlphaValue_(0.0)
        NSAnimationContext.endGrouping()
        AppHelper.callAfter(0.26, self._hide)

    def _hide(self):
        if self._window:
            self._window.orderOut_(None)

    def _build(self):
        SZ = self.SZ
        rect = NSMakeRect(0, 0, SZ, SZ)

        # --- window (borderless, fully transparent) ---
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

        # --- frosted glass view ---
        effect = NSVisualEffectView.alloc().initWithFrame_(rect)
        effect.setMaterial_(22)   # NSVisualEffectMaterialHUDWindow — dark frosted
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        win.setContentView_(effect)

        # Apply corner radius AFTER adding to window so the layer is live.
        # Using CALayer mask for a pixel-perfect clip (no edge colour bleed).
        effect.setWantsLayer_(True)
        layer = effect.layer()
        layer.setCornerRadius_(self.RADIUS)
        layer.setMasksToBounds_(True)
        layer.setCornerCurve_("continuous")   # iOS-style squircle

        # --- SF Symbol icon (centred in upper ~60% of tile) ---
        icon_sz  = 72
        icon_x   = (SZ - icon_sz) / 2
        icon_y   = SZ - icon_sz - 12          # 12 pt from top
        iv = _image_view(
            NSMakeRect(icon_x, icon_y, icon_sz, icon_sz),
            "speaker.wave.3.fill", 52, NSColor.whiteColor()
        )
        effect.addSubview_(iv)
        self._icon_view = iv

        # --- text label (centred in lower ~30%) ---
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


# -------------------------------------------------------------------
# Onboarding / gesture reference sheet
# -------------------------------------------------------------------
class OnboardingWindow:
    """Gesture reference sheet. Thread-safe."""

    def __init__(self):
        self._window     = None
        self._btn_target = None

    def show(self):
        AppHelper.callAfter(self._show_main)

    def _show_main(self):
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
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("Waiv — Gesture Guide")
        win.setLevel_(NSFloatingWindowLevel)
        win.setTitlebarAppearsTransparent_(True)

        effect = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        effect.setMaterial_(18)   # under-page background — light/neutral
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        win.setContentView_(effect)

        # Title
        self._lbl(effect, "Waiv Gesture Control",
                  NSMakeRect(20, H - 62, W - 40, 36), size=18, bold=True)
        self._lbl(effect, "Hold any gesture steady for 2 seconds to trigger it.",
                  NSMakeRect(20, H - 90, W - 40, 26),
                  size=12, color=NSColor.secondaryLabelColor())

        # Divider
        div = NSTextField.alloc().initWithFrame_(NSMakeRect(20, H - 100, W - 40, 1))
        div.setEditable_(False)
        div.setBordered_(False)
        div.setDrawsBackground_(True)
        div.setBackgroundColor_(NSColor.separatorColor())
        effect.addSubview_(div)

        # Gesture rows — SF Symbol icon + name + action
        ROW_H = 46
        y = H - 112
        for symbol, name, action in ONBOARDING_ROWS:
            iv = _image_view(
                NSMakeRect(16, y + 4, 32, 32),
                symbol, 20, NSColor.labelColor()
            )
            effect.addSubview_(iv)
            self._lbl(effect, name,   NSMakeRect(58, y + 14, 160, 22), size=14, bold=True)
            self._lbl(effect, action, NSMakeRect(228, y + 14, W - 250, 22),
                      size=13, color=NSColor.secondaryLabelColor())
            y -= ROW_H

        # "Got it" button
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(W // 2 - 55, 18, 110, 32))
        btn.setTitle_("Got it")
        btn.setBezelStyle_(NSBezelStyleRounded)

        target = _ButtonTarget.alloc().init()
        target._cb = lambda: (mark_onboarded(), win.orderOut_(None))
        self._btn_target = target
        btn.setTarget_(target)
        btn.setAction_("doAction:")
        effect.addSubview_(btn)

        self._window = win

    @staticmethod
    def _lbl(parent, text, frame, size=14, bold=False, color=None):
        f = NSTextField.alloc().initWithFrame_(frame)
        f.setStringValue_(text)
        f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold
                   else NSFont.systemFontOfSize_(size))
        if color:
            f.setTextColor_(color)
        f.setEditable_(False)
        f.setBordered_(False)
        f.setDrawsBackground_(False)
        parent.addSubview_(f)
        return f
