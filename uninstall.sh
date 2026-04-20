#!/bin/bash
# Waiv — full uninstall
# Removes: LaunchAgent, app bundle, config, logs, and resets TCC permissions.

PLIST_NAME="com.waiv.gesture.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
APP_PATH="/Applications/Waiv.app"
CONFIG_DIR="$HOME/.config/waiv"
BUNDLE_ID="com.waiv.gesture"

echo "==> Stopping Waiv..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true
pkill -f "gesture_app.py" 2>/dev/null || true

echo "==> Removing LaunchAgent..."
rm -f "$PLIST_PATH"

echo "==> Removing app..."
rm -rf "$APP_PATH"

echo "==> Removing config and logs..."
rm -rf "$CONFIG_DIR"
rm -f /tmp/waiv.log /tmp/waiv-error.log

echo "==> Resetting TCC permissions (Camera, Accessibility)..."
tccutil reset Camera   "$BUNDLE_ID" 2>/dev/null || true
tccutil reset Camera   "org.python.python" 2>/dev/null || true

echo ""
echo "Waiv fully removed."
echo ""
echo "Note: To remove Accessibility permission, go to:"
echo "  System Settings → Privacy & Security → Accessibility"
echo "  and remove Waiv manually (macOS does not allow scripts to remove it)."
