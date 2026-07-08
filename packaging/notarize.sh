#!/bin/bash
# Notarize a .app or .dmg with Apple
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <path-to-app-or-dmg>"
    echo "Requires environment variables: APPLE_ID, TEAM_ID, APP_SPECIFIC_PASSWORD"
    exit 1
fi

FILE="$1"

if [ -z "$APPLE_ID" ] || [ -z "$TEAM_ID" ] || [ -z "$APP_SPECIFIC_PASSWORD" ]; then
    echo "Error: Set APPLE_ID, TEAM_ID, and APP_SPECIFIC_PASSWORD environment variables"
    exit 1
fi

echo "=== Notarizing $FILE ==="

# Submit for notarization
xcrun notarytool submit "$FILE" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --password "$APP_SPECIFIC_PASSWORD" \
    --wait

# Staple the notarization ticket (for .dmg)
if [[ "$FILE" == *.dmg ]]; then
    echo "Stapling ticket..."
    xcrun stapler staple "$FILE"
fi

echo "=== Done ==="
