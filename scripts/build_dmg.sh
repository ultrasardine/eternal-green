#!/usr/bin/env bash
# Build a distributable DMG for Eternal Green.
#
# Usage:
#   bash scripts/build_dmg.sh
#
# Prerequisites:
#   - PyInstaller must have already produced dist/Eternal Green.app
#   - hdiutil (ships with macOS)

set -euo pipefail

APP_NAME="Eternal Green"
DMG_NAME="EternalGreen"
VERSION=$(uv run python -c "import eternal_green; print(eternal_green.__version__)")
DMG_FILE="dist/${DMG_NAME}-${VERSION}.dmg"
VOLUME_NAME="${APP_NAME} ${VERSION}"
APP_PATH="dist/${APP_NAME}.app"

if [ ! -d "$APP_PATH" ]; then
    echo "Error: ${APP_PATH} not found. Run 'make build' first."
    exit 1
fi

echo "Creating DMG: ${DMG_FILE}"

# Remove old DMG if present
rm -f "$DMG_FILE"

# Create a temporary directory for the DMG contents
STAGING=$(mktemp -d)
cp -R "$APP_PATH" "$STAGING/"

# Create a symbolic link to /Applications for drag-install
ln -s /Applications "$STAGING/Applications"

# Build the DMG
hdiutil create \
    -volname "$VOLUME_NAME" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DMG_FILE"

rm -rf "$STAGING"

echo "Done: ${DMG_FILE}"
