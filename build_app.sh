#!/bin/bash
# Build Network Monitor.app for macOS
#
# This creates a native macOS app bundle that uses Python.framework 3.10
# (which has working Tk/Tcl) instead of uv Python (which has Tk issues).

# Get script directory (assuming script is in project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Start build timer
BUILD_START=$(date +%s)

APP_NAME="Network Monitor"
APP_DIR="${SCRIPT_DIR}/dist/${APP_NAME}.app"
CONTENTS_DIR="${APP_DIR}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

# Clean old build
rm -rf "${APP_DIR}"

# Create app structure
mkdir -p "${MACOS_DIR}"
mkdir -p "${RESOURCES_DIR}"

# Convert PNG icon to .icns format (with caching)
ICON_SOURCE="${SCRIPT_DIR}/resources/network-monitor-icon.png"
ICON_CACHE="${SCRIPT_DIR}/dist/.icon_cache.icns"
ICON_ICNS="${RESOURCES_DIR}/AppIcon.icns"

if [ -f "${ICON_SOURCE}" ]; then
    # Skip conversion if cached .icns exists and is newer than source
    if [ -f "${ICON_CACHE}" ] && [ "${ICON_CACHE}" -nt "${ICON_SOURCE}" ]; then
        cp "${ICON_CACHE}" "${ICON_ICNS}"
        echo "✓ Using cached icon"
    else
        echo "Converting icon to .icns format..."
        ICON_START=$(date +%s)
        # Create temporary iconset directory (must end in .iconset)
        ICONSET_DIR=$(mktemp -d).iconset
        mkdir -p "${ICONSET_DIR}"
        
        # Use minimal essential sizes only - 5 images for fastest conversion
        # Process in parallel for maximum speed
        sips -z 16 16   "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_16x16.png" > /dev/null 2>&1 &
        sips -z 32 32   "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_16x16@2x.png" > /dev/null 2>&1 &
        sips -z 128 128 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_128x128.png" > /dev/null 2>&1 &
        sips -z 256 256 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_256x256.png" > /dev/null 2>&1 &
        sips -z 512 512 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_512x512.png" > /dev/null 2>&1 &
        
        # Wait for all background jobs to complete
        wait
        
        # Convert iconset to .icns (iconutil expects directory name ending in .iconset)
        # Use quiet mode and redirect stderr for faster execution
        iconutil -c icns "${ICONSET_DIR}" -o "${ICON_ICNS}" 2>/dev/null
        
        # Clean up temporary directory immediately
        TEMP_BASE="${ICONSET_DIR%.iconset}"
        rm -rf "${TEMP_BASE}"* 2>/dev/null
        
        ICON_END=$(date +%s)
        ICON_DURATION=$((ICON_END - ICON_START))
        if [ -f "${ICON_ICNS}" ]; then
            # Cache the icon for next build
            cp "${ICON_ICNS}" "${ICON_CACHE}"
            echo "✓ Icon converted successfully (${ICON_DURATION}s)"
        else
            echo "⚠ Warning: Icon conversion failed, app will use default icon"
        fi
    fi
else
    echo "⚠ Warning: Icon source not found at ${ICON_SOURCE}, app will use default icon"
fi

# Copy source code to Resources
cp -r "${SCRIPT_DIR}/src/netmonitor" "${RESOURCES_DIR}/"

# Create shell script launcher
echo "Creating launcher..."
cp "${SCRIPT_DIR}/launcher.sh" "${MACOS_DIR}/Network Monitor"
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

BUILD_END=$(date +%s)
BUILD_DURATION=$((BUILD_END - BUILD_START))

echo "✓ Created ${APP_NAME}.app in dist/"
echo ""
echo "Build completed in ${BUILD_DURATION}s"
echo ""

# Prompt user to install to /Applications/
read -p "Install to /Applications/? [Y/n] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Skipping installation."
    echo ""
    echo "To install manually:"
    echo "  cp -r \"${APP_DIR}\" /Applications/"
    echo ""
    echo "Or open it directly:"
    echo "  open \"${APP_DIR}\""
else
    echo "Installing to /Applications/..."
    cp -r "${APP_DIR}" /Applications/
    if [ $? -eq 0 ]; then
        echo "✓ Installed successfully!"
    else
        echo "✗ Installation failed"
        exit 1
    fi
fi

