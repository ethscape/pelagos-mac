#!/bin/bash
# Watch Pelagos logs in real-time

LOG_DIR="$HOME/Library/Logs"

echo "🌊 Pelagos Log Viewer"
echo "===================="
echo ""
echo "Press Ctrl+C to exit"
echo ""

# Check which logs exist
if [ -f "$LOG_DIR/pelagos.log" ]; then
    echo "📋 Watching main log: $LOG_DIR/pelagos.log"
    echo ""
    tail -f "$LOG_DIR/pelagos.log"
elif [ -f "$LOG_DIR/pelagos.stdout.log" ] || [ -f "$LOG_DIR/pelagos.stderr.log" ]; then
    echo "📋 Watching stdout and stderr logs..."
    echo ""
    tail -f "$LOG_DIR/pelagos.stdout.log" "$LOG_DIR/pelagos.stderr.log" 2>/dev/null
else
    echo "❌ No log files found yet. The daemon may not have started."
    echo ""
    echo "Expected log locations:"
    echo "  - $LOG_DIR/pelagos.log"
    echo "  - $LOG_DIR/pelagos.stdout.log"
    echo "  - $LOG_DIR/pelagos.stderr.log"
    exit 1
fi
