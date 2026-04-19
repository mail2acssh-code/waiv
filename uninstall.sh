#!/bin/bash
# Waiv Gesture Control — uninstall
set -e

PLIST_NAME="com.waiv.gesture.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "==> Stopping and removing LaunchAgent..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"

echo ""
echo "Waiv uninstalled. The source folder has not been deleted."
echo "To fully remove: cd .. && rm -rf waiv"
