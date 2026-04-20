"""
py2app build config for Waiv Gesture Control.

Build:
    venv/bin/python setup.py py2app

Output: dist/Waiv.app
"""

import glob
from setuptools import setup

APP     = ["launcher.py"]
VERSION = "1.0.4"

DATA_FILES = [
    ("", [
        "hand_landmarker.task",
        "gesture_app.py",
        "gesture_classifier.py",
        "media_controller.py",
        "media_detector.py",
        "hud.py",
        "plugin_loader.py",
    ]),
    # plugins/ must land as real .py files (not frozen) so plugin_loader
    # can discover them at runtime with pkgutil.iter_modules.
    ("plugins", glob.glob("plugins/*.py")),
]

OPTIONS = {
    "iconfile": "docs/waiv.icns",
    "plist": {
        "CFBundleName":               "Waiv",
        "CFBundleDisplayName":        "Waiv",
        "CFBundleIdentifier":         "com.waiv.gesture",
        "CFBundleVersion":            VERSION,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement":                True,
        "LSMinimumSystemVersion":     "12.0",
        "NSCameraUsageDescription": (
            "Waiv uses the camera to detect hand gestures "
            "for controlling media playback and volume."
        ),
        "NSAppleEventsUsageDescription": (
            "Waiv uses Apple Events to control system volume."
        ),
    },
    "packages": [
        "mediapipe",
        "cv2",
        "numpy",
        "setproctitle",
    ],
    "includes": [
        "gesture_classifier",
        "media_controller",
        "media_detector",
        "gesture_app",
        "plugin_loader",
        "launcher",
        "hud",
        "plistlib",
    ],
    "excludes": ["tkinter"],
    "argv_emulation": False,
    "semi_standalone": False,
}

setup(
    name="Waiv",
    version=VERSION,
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
