#!/bin/bash
# Pelagos Installation Script

set -e

echo "🌊 Pelagos Installation"
echo "======================="
echo ""

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_FILE="$SCRIPT_DIR/com.pelagos.daemon.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
INSTALLED_PLIST="$LAUNCH_AGENTS_DIR/com.pelagos.daemon.plist"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"

# Create virtual environment if it doesn't exist
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "🔨 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Banner notification system uses terminal-notifier (no Xcode build needed)
echo ""
echo "🔔 Banner notification system uses terminal-notifier"
echo "   ✓ No additional build steps required"

# Make the daemon script executable
echo ""
echo "🔧 Making daemon script executable..."
chmod +x "$SCRIPT_DIR/pelagos_daemon.py"
chmod +x "$SCRIPT_DIR/Pelagos.app/Contents/MacOS/Pelagos"

# No saved state cleanup needed for terminal-notifier

# Register app bundle with Launch Services for icon/name metadata
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
    echo ""
    echo "🖼  Registering Pelagos app with Launch Services..."
    "$LSREGISTER" -f "$SCRIPT_DIR/Pelagos.app"
fi

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$LAUNCH_AGENTS_DIR"

# Check if daemon is already installed
if [ -f "$INSTALLED_PLIST" ]; then
    echo ""
    echo "⚠️  Daemon is already installed. Unloading existing daemon..."
    launchctl unload "$INSTALLED_PLIST" 2>/dev/null || true
fi

# Copy plist file
echo ""
echo "📋 Installing daemon..."
cp "$PLIST_FILE" "$INSTALLED_PLIST"

# Load the daemon
echo ""
echo "🚀 Starting daemon..."
launchctl load "$INSTALLED_PLIST"

# Check if daemon is running
sleep 2
if launchctl list | grep -q "com.pelagos.daemon"; then
    echo ""
    echo "✅ Pelagos daemon installed and running successfully!"
    echo ""
    echo "📝 Logs can be found at:"
    echo "   - Main log: ~/Library/Logs/pelagos.log"
    echo "   - Stdout: ~/Library/Logs/pelagos.stdout.log"
    echo "   - Stderr: ~/Library/Logs/pelagos.stderr.log"
    echo ""
    echo "🔧 To stop the daemon:"
    echo "   launchctl unload ~/Library/LaunchAgents/com.pelagos.daemon.plist"
    echo ""
    echo "🔧 To restart the daemon:"
    echo "   launchctl unload ~/Library/LaunchAgents/com.pelagos.daemon.plist"
    echo "   launchctl load ~/Library/LaunchAgents/com.pelagos.daemon.plist"
else
    echo ""
    echo "❌ Daemon failed to start. Check the logs for details:"
    echo "   tail -f ~/Library/Logs/pelagos.stderr.log"
    exit 1
fi
