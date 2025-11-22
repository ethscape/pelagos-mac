# Pelagos Quick Reference

## Watch Logs (Real-time)
```bash
./watch-logs.sh
```

## Daemon Control

### Check Status
```bash
launchctl list | grep pelagos
```

### Stop Daemon
```bash
launchctl unload ~/Library/LaunchAgents/com.pelagos.daemon.plist
```

### Start Daemon
```bash
launchctl load ~/Library/LaunchAgents/com.pelagos.daemon.plist
```

### Restart Daemon (after config changes)
```bash
launchctl unload ~/Library/LaunchAgents/com.pelagos.daemon.plist
launchctl load ~/Library/LaunchAgents/com.pelagos.daemon.plist
```

## Manual Testing
```bash
./venv/bin/python3 pelagos_daemon.py
```

## Log Locations
- Main: `~/Library/Logs/pelagos.log`
- Stdout: `~/Library/Logs/pelagos.stdout.log`
- Stderr: `~/Library/Logs/pelagos.stderr.log`

## How to Test
1. Download a file from hitomi.la
2. Watch the logs: `./watch-logs.sh`
3. File should be transferred to mahoro and deleted locally

## Troubleshooting

### Check if daemon is running
```bash
launchctl list | grep pelagos
```

### View recent errors
```bash
tail -20 ~/Library/Logs/pelagos.stderr.log
```

### Test SSH connection
```bash
ssh -i /path/to/private/key username@hostname
```

### Reinstall
```bash
./install.sh
```
