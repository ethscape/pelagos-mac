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

# Install alerter for banner notifications
echo ""
echo "🔔 Installing alerter for banner notifications..."
ALERTER_DIR="$HOME/.local/bin"
mkdir -p "$ALERTER_DIR"

# Check if alerter is already installed
if [ ! -f "$ALERTER_DIR/alerter" ]; then
    echo "📥 Downloading alerter..."
    cd /tmp
    # Get the latest release download URL (alerter only provides amd64 builds for macOS)
    RELEASE_URL=$(curl -s https://api.github.com/repos/vjeantet/alerter/releases/latest | grep "browser_download_url.*darwin_amd64" | cut -d '"' -f 4)
    if [ -z "$RELEASE_URL" ]; then
        echo "❌ Could not find alerter release for macOS"
        exit 1
    fi
    curl -L -o alerter.gz "$RELEASE_URL"
    gunzip -c alerter.gz > "$ALERTER_DIR/alerter"
    chmod +x "$ALERTER_DIR/alerter"
    rm alerter.gz
    echo "✓ Alerter installed to $ALERTER_DIR/alerter"
else
    echo "✓ Alerter already installed"
fi

# Add ~/.local/bin to PATH if not already there
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
    echo "✓ Added ~/.local/bin to PATH in .zshrc"
fi

# Check notification port availability
echo ""
echo "🔌 Checking notification port availability..."
CONFIG_FILE="$SCRIPT_DIR/config.json"
DEFAULT_PORT=9999
MAX_PORT=10010

# Function to check if port is available
check_port() {
    local port=$1
    if lsof -i :$port >/dev/null 2>&1; then
        return 1  # Port is in use
    else
        return 0  # Port is available
    fi
}

# Function to check if Pelagos is using the port
check_pelagos_on_port() {
    local port=$1
    local pid=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pid" ]; then
        # Check the full command line for pelagos_daemon.py
        local cmdline=$(ps -p $pid -o command= 2>/dev/null)
        if echo "$cmdline" | grep -q "pelagos_daemon.py"; then
            return 0  # Pelagos is using the port
        fi
    fi
    return 1  # Either port not in use or not Pelagos
}

# Function to stop existing Pelagos daemon
stop_pelagos_daemon() {
    echo "🛑 Stopping existing Pelagos daemon..."
    if launchctl list | grep -q "com.pelagos.daemon"; then
        launchctl unload "$HOME/Library/LaunchAgents/com.pelagos.daemon.plist" 2>/dev/null || true
        echo "✓ Unloaded daemon from launchctl"
    fi
    
    # Kill any remaining pelagos processes
    local pids=$(pgrep -f "pelagos_daemon.py" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill 2>/dev/null || true
        echo "✓ Terminated remaining daemon processes"
    fi
    
    # Wait a moment for processes to stop
    sleep 2
}

# Function to find an available port
find_available_port() {
    local start_port=$1
    local end_port=$2
    
    for port in $(seq $start_port $end_port); do
        if check_port $port; then
            echo $port
            return 0
        fi
    done
    return 1
}

# Read current port from config.json
CURRENT_PORT=$DEFAULT_PORT
if [ -f "$CONFIG_FILE" ]; then
    CURRENT_PORT=$(python3 -c "
import json
try:
    with open('$CONFIG_FILE', 'r') as f:
        config = json.load(f)
        print(config.get('port', $DEFAULT_PORT))
except:
    print($DEFAULT_PORT)
" 2>/dev/null || echo $DEFAULT_PORT)
fi

# Check if current port is available
if ! check_port $CURRENT_PORT; then
    echo "⚠️  Port $CURRENT_PORT is already in use"
    
    # Check if Pelagos is using the port
    if check_pelagos_on_port $CURRENT_PORT; then
        echo ""
        echo "🤖 Pelagos daemon is already running on port $CURRENT_PORT"
        echo ""
        read -p "Would you like to stop the existing daemon and continue? (y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            stop_pelagos_daemon
            
            # Check if port is now available
            if check_port $CURRENT_PORT; then
                echo "✓ Port $CURRENT_PORT is now available"
            else
                echo "⚠️  Port $CURRENT_PORT is still in use after stopping daemon"
                # Fall through to suggest alternative port
            fi
        else
            echo "⚠️  Continuing with port $CURRENT_PORT (may cause conflicts)"
        fi
    fi
    
    # If port is still in use, suggest alternative
    if ! check_port $CURRENT_PORT; then
        # Find an available port
        AVAILABLE_PORT=$(find_available_port $DEFAULT_PORT $MAX_PORT)
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "💡 Suggestion: Use port $AVAILABLE_PORT instead"
            echo ""
            echo "To update your configuration, edit $CONFIG_FILE and update:"
            echo ""
            echo "{"
            echo "    \"port\": $AVAILABLE_PORT,"
            echo "    \"sources\": [],"
            echo "    \"commonActions\": []"
            echo "}"
            echo ""
            read -p "Would you like to update the config file now? (y/N): " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                # Update the config file
                python3 -c "
import json

try:
    with open('$CONFIG_FILE', 'r') as f:
        config = json.load(f)
except:
    config = {}

config['port'] = $AVAILABLE_PORT

# Ensure sources and commonActions exist
if 'sources' not in config:
    config['sources'] = []
if 'commonActions' not in config:
    config['commonActions'] = []

with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=4)

print('✓ Updated config.json with port $AVAILABLE_PORT')
"
                CURRENT_PORT=$AVAILABLE_PORT
            else
                echo "⚠️  Continuing with port $CURRENT_PORT (may cause conflicts)"
            fi
        else
            echo "❌ No available ports found in range $DEFAULT_PORT-$MAX_PORT"
            echo "   Please free up a port in this range and try again"
            exit 1
        fi
    fi
else
    echo "✓ Port $CURRENT_PORT is available"
fi

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

# Create dynamic plist with correct paths
echo ""
echo "📋 Installing daemon..."
# Replace hardcoded paths in plist
sed -e "s|/path/to/pelagos|$SCRIPT_DIR|g" \
    -e "s|/logs_folder|$HOME/Library/Logs|g" \
    "$PLIST_FILE" > "$INSTALLED_PLIST"

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
