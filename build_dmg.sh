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
    echo "Run:   python3 -m venv venv && source venv/bin/activate"
    echo "Then:  pip install -r requirements.txt py2app"
    exit 1
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

# ── Step 5: package as DMG ────────────────────────────────────────────────────
echo "==> Creating DMG..."

STAGING="dist/_dmg_staging"
FINAL_DMG="dist/$DMG_NAME"

rm -rf "$STAGING"
mkdir "$STAGING"
cp -r "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create \
    -volname "Waiv" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$FINAL_DMG"

rm -rf "$STAGING"

echo ""
echo "Done!  dist/$DMG_NAME  ($(du -sh "dist/$DMG_NAME" | cut -f1))"
echo ""
echo "Next steps:"
echo "  1. Test:   open $APP_PATH"
echo "  2. Release: gh release create v${VERSION} dist/$DMG_NAME \\"
echo "                 --title 'Waiv ${VERSION}' --generate-notes"
echo "  3. Update the download link in docs/index.html"
