#!/bin/bash
# Build Ink (Part 1) into .app and .dmg
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
INK_DIR="$ROOT_DIR/ink"

echo "=== Building Ink (Part 1: System-Wide Inking) ==="

cd "$INK_DIR"
rm -rf build dist

# Build .app
echo "Running py2app..."
python setup.py py2app
if [ $? -ne 0 ]; then
    echo "py2app failed"
    exit 1
fi

# Copy local modules into the app bundle's Resources directory
RESOURCES="$INK_DIR/dist/Ink.app/Contents/Resources"
echo "Copying local modules into bundle..."

mkdir -p "$RESOURCES/core"
cp "$ROOT_DIR/core/"*.py "$RESOURCES/core/"

mkdir -p "$RESOURCES/gui"
cp "$INK_DIR/gui/"*.py "$RESOURCES/gui/"

cp "$INK_DIR/ink.png" "$RESOURCES/"

echo "Local modules copied."

# Remove quarantine attributes (needed for unsigned apps)
xattr -cr dist/Ink.app

# Codesign (optional)
if [ -n "$CODESIGN_IDENTITY" ]; then
    echo "Codesigning..."
    codesign --force --deep --sign "$CODESIGN_IDENTITY" \
        --entitlements "$SCRIPT_DIR/entitlements.plist" \
        --options runtime \
        dist/Ink.app
fi

# Create DMG
echo "Creating DMG..."
hdiutil create -volname "Ink" \
    -srcfolder dist/Ink.app \
    -ov -format UDZO \
    dist/Ink.dmg

echo "=== Done: dist/Ink.dmg ==="
