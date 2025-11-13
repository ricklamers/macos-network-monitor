#!/bin/bash
# Build Network Monitor.app for macOS
#
# This creates a native macOS app bundle that uses Python.framework 3.10
# (which has working Tk/Tcl) instead of uv Python (which has Tk issues).

APP_NAME="Network Monitor"
APP_DIR="/Users/rick/workspace/sandbox/netmonitor/dist/${APP_NAME}.app"
CONTENTS_DIR="${APP_DIR}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

# Clean old build
rm -rf "${APP_DIR}"

# Create app structure
mkdir -p "${MACOS_DIR}"
mkdir -p "${RESOURCES_DIR}"

# Convert PNG icon to .icns format
ICON_SOURCE="/Users/rick/workspace/sandbox/netmonitor/resources/network-monitor-icon.png"
ICON_ICNS="${RESOURCES_DIR}/AppIcon.icns"

if [ -f "${ICON_SOURCE}" ]; then
    echo "Converting icon to .icns format..."
    # Create temporary iconset directory (must end in .iconset)
    ICONSET_DIR=$(mktemp -d).iconset
    mkdir -p "${ICONSET_DIR}"
    
    # Create iconset with required sizes (iconutil expects specific filenames)
    sips -z 16 16     "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_16x16.png" > /dev/null 2>&1
    sips -z 32 32     "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_16x16@2x.png" > /dev/null 2>&1
    sips -z 32 32     "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_32x32.png" > /dev/null 2>&1
    sips -z 64 64     "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_32x32@2x.png" > /dev/null 2>&1
    sips -z 128 128   "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_128x128.png" > /dev/null 2>&1
    sips -z 256 256   "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_128x128@2x.png" > /dev/null 2>&1
    sips -z 256 256   "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_256x256.png" > /dev/null 2>&1
    sips -z 512 512   "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_256x256@2x.png" > /dev/null 2>&1
    sips -z 512 512   "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_512x512.png" > /dev/null 2>&1
    sips -z 1024 1024 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_512x512@2x.png" > /dev/null 2>&1
    
    # Convert iconset to .icns (iconutil expects directory name ending in .iconset)
    iconutil -c icns "${ICONSET_DIR}" -o "${ICON_ICNS}" 2>/dev/null
    
    # Clean up temporary directory
    TEMP_BASE="${ICONSET_DIR%.iconset}"
    rm -rf "${TEMP_BASE}"*
    
    if [ -f "${ICON_ICNS}" ]; then
        echo "✓ Icon converted successfully"
    else
        echo "⚠ Warning: Icon conversion failed, app will use default icon"
    fi
else
    echo "⚠ Warning: Icon source not found at ${ICON_SOURCE}, app will use default icon"
fi

# Copy source code to Resources
cp -r /Users/rick/workspace/sandbox/netmonitor/src/netmonitor "${RESOURCES_DIR}/"

# Create shell script launcher
echo "Creating launcher..."
cp /Users/rick/workspace/sandbox/netmonitor/launcher.sh "${MACOS_DIR}/Network Monitor"
chmod +x "${MACOS_DIR}/Network Monitor"

if [ $? -eq 0 ]; then
    echo "✓ Launcher created successfully"
else
    echo "✗ Launcher creation failed"
    exit 1
fi

# Create PkgInfo file
echo -n "APPL????" > "${CONTENTS_DIR}/PkgInfo"

# Create Info.plist
cat > "${CONTENTS_DIR}/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Network Monitor</string>
    <key>CFBundleIdentifier</key>
    <string>com.netmonitor.app</string>
    <key>CFBundleName</key>
    <string>Network Monitor</string>
    <key>CFBundleDisplayName</key>
    <string>Network Monitor</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
</dict>
</plist>
EOF

echo "✓ Created ${APP_NAME}.app in dist/"
echo ""
echo "To install:"
echo "  cp -r \"${APP_DIR}\" /Applications/"
echo ""
echo "Or open it directly:"
echo "  open \"${APP_DIR}\""

