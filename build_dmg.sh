#!/bin/bash
# Waiv Gesture Control — build Waiv.app and package as a DMG
#
# Prerequisites (run once):
#   python3 -m venv venv
#   source venv/bin/activate
#   pip install -r requirements.txt py2app
#
# Usage:
#   bash build_dmg.sh [version]   (version defaults to 1.0.0)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="${1:-1.0.0}"
DMG_NAME="Waiv-${VERSION}.dmg"
MODEL_FILE="hand_landmarker.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

echo "==> Building Waiv ${VERSION}"

# ── Step 1: venv check ────────────────────────────────────────────────────────
if [ ! -f venv/bin/python ]; then
    echo "ERROR: venv not found."
    echo ""
    echo "IMPORTANT: Use the official Python.org installer, NOT Homebrew Python."
    echo "Homebrew Python on macOS 26 beta compiles with minos 26.0, making the"
    echo "app incompatible with stable macOS releases."
    echo ""
    echo "  1. Download Python 3.11 from https://www.python.org/downloads/"
    echo "  2. /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 -m venv venv"
    echo "  3. source venv/bin/activate"
    echo "  4. pip install -r requirements.txt py2app"
    exit 1
fi

# Warn if the venv Python has a macOS 26+ minimum target
VENV_MINOS=$(otool -l venv/bin/python3* 2>/dev/null | grep minos | head -1 | awk '{print $2}' || echo "")
if [[ "$VENV_MINOS" == 26* ]]; then
    echo "WARNING: venv Python has minos ${VENV_MINOS} — app will only run on macOS 26+."
    echo "         For a distributable build, recreate the venv with the python.org installer."
    echo "         Continuing anyway..."
    echo ""
fi

# ── Step 2: model file ────────────────────────────────────────────────────────
if [ ! -f "$MODEL_FILE" ]; then
    echo "==> Downloading hand-landmark model (~29 MB)..."
    curl -L --progress-bar "$MODEL_URL" -o "$MODEL_FILE"
else
    echo "==> Model file present."
fi

# ── Step 3: clean previous build ─────────────────────────────────────────────
echo "==> Cleaning previous build..."
rm -rf build dist

# ── Step 4: build .app with py2app ────────────────────────────────────────────
echo "==> Running py2app..."
venv/bin/python setup.py py2app --no-strip 2>&1 | tail -10

APP_PATH="dist/Waiv.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: py2app did not produce dist/Waiv.app"
    exit 1
fi
echo "    Built: $APP_PATH"

# ── Step 5: code sign ─────────────────────────────────────────────────────────
# Try Developer ID signing first; fall back to ad-hoc so the signature is valid.
SIGN_ID=""
if security find-identity -v -p codesigning 2>/dev/null | grep -q "Developer ID Application"; then
    SIGN_ID=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | awk -F'"' '{print $2}')
    echo "==> Signing with Developer ID: $SIGN_ID"
    codesign --force --deep --options runtime \
        --entitlements entitlements.plist \
        --sign "$SIGN_ID" \
        "$APP_PATH"
    echo "    NOTE: Submit for notarization with 'xcrun notarytool' before releasing."
else
    echo "==> No Developer ID found — applying ad-hoc signature."
    echo "    Users will need to right-click → Open (or System Settings → Privacy & Security → Open Anyway)."
    # Sign each dylib individually first; some have linker signatures that need --no-strict
    find "$APP_PATH" \( -name "*.dylib" -o -name "*.so" \) | while read lib; do
        codesign --force --sign - "$lib" 2>/dev/null || \
        codesign --force --sign - --no-strict "$lib" 2>/dev/null || true
    done
    # Sign frameworks
    find "$APP_PATH" -name "*.framework" | while read fw; do
        codesign --force --deep --sign - "$fw" 2>/dev/null || true
    done
    # Sign the app bundle (allow partial success with --no-strict for linker-signed libs)
    codesign --force --sign - --no-strict "$APP_PATH" 2>&1 || \
        echo "    (Ad-hoc signing had warnings — app will still run locally)"
fi

# ── Step 6: package as DMG ────────────────────────────────────────────────────
echo "==> Creating DMG..."

STAGING="dist/_dmg_staging"
FINAL_DMG="dist/$DMG_NAME"

rm -rf "$STAGING"
mkdir "$STAGING"
cp -r "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

cat > "$STAGING/README.txt" << 'READMEEOF'
Waiv — Installation
====================

1. Drag Waiv.app into the Applications folder.

2. Open Terminal (Applications → Utilities → Terminal) and run:

      xattr -cr /Applications/Waiv.app

3. Open Waiv.app — the setup wizard will guide you through
   Camera and Accessibility permissions.

Waiv lives in your menu bar (✋) once set up.
Use the menu bar icon → "Uninstall Waiv" to remove it cleanly.
READMEEOF

hdiutil create \
    -volname "Waiv" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$FINAL_DMG"

rm -rf "$STAGING"

# Also copy as Waiv.dmg so the "latest/download/Waiv.dmg" GitHub link always works
cp "dist/$DMG_NAME" "dist/Waiv.dmg"

echo ""
echo "Done!  dist/$DMG_NAME  ($(du -sh "dist/$DMG_NAME" | cut -f1))"
echo ""
echo "Next steps:"
echo "  1. Test:   open $APP_PATH"
echo "  2. Release: gh release create v${VERSION} dist/$DMG_NAME dist/Waiv.dmg \\"
echo "                 --title 'Waiv ${VERSION}' --generate-notes"
