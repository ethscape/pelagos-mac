# Pelagos

A macOS daemon that monitors your Downloads folder and automatically transfers files to remote servers based on their source URL or other criteria.

## Features

- Monitors Downloads folder for new files
- Checks the "Where from" metadata of downloaded files
- Matches files against configured sources
- Supports SCP transfer action
- Banner notifications using alerter with image preview
- Interactive notification system with click-to-execute
- Runs as a background daemon using launchd

## Installation

### 1. Run the Installation Script

The easiest way to install:

```bash
cd /path/to/pelagos
./install.sh
```

This will:
- Create a virtual environment
- Install Python dependencies
- Install alerter for banner notifications
- Make scripts executable
- Install and start the daemon
- Register the Pelagos app wrapper so the daemon appears with name and icon in System Settings
- Register the Pelagos app so Launch Services knows about its icon

### 2. Configure SSH Access

Ensure your SSH key is set up for passwordless authentication to the target server:

```bash
# Test SSH connection
ssh -i /path/to/private/key username@hostname
```

## Configuration

Edit `config.json` to configure sources and actions:

```json
{
    "sources": [
        {
            "name": "mymangasite",
            "url": "https://mymangasite.com",
            "tags": ["Manga"],
            "action": {
                "type": "scp",
                "target": "hostname:/path/to/destination",
                "username": "username",
                "privateKey": "/path/to/private/key",
                "keepOriginal": false,
                "rename": "{{title}}.{{extension}}",
                "overwriteRule": "rename"
            }
        },
        {
            "name": "anothermangasite",
            "url": "https://anothermangasite.com",
            "tags": ["Manga"],
            "action": {
                "type": "common",
                "commonAction": "Manga"
            }
        }
    ],
    "commonActions": [
        {
            "name": "Manga",
            "type": "scp",
            "target": "hostname:/path/to/destination",
            "username": "username",
            "privateKey": "/path/to/private/key",
            "keepOriginal": false,
            "rename": "{{title}}.{{extension}}",
            "overwriteRule": "rename",
            "auto": false,
            "filters": [
                {
                    "type": "regex",
                    "pattern": "^.*\\.(cb.|zip|rar)$"
                },
                {
                    "type": "noSource"
                },
                {
                    "type": "hook",
                    "name": "isMagazine"
                }
            ]
        }
    ]
}
```

### Configuration Options

- **name**: Friendly name for the source
- **url**: Base URL to match against
- **tags**: Optional tags for organization
- **action.type**: Action type (currently "scp" or `"common"` for referencing a common action template)
- **action.target**: SCP target in format `host:/path`
- **action.username**: SSH username
- **action.privateKey**: Path to SSH private key
- **keepOriginal**: If `false`, deletes the original file after successful transfer
- **rename**: Template for renaming (currently uses original filename)
- **overwriteRule**: How to handle existing files (future feature)
- **auto**:
  - If `true`, the action executes immediately without user interaction.
  - If `false`, Pelagos shows a **banner notification** with the action details.
  - Click the notification body (for single actions) or use the dropdown (multiple actions) to execute.
  - Notifications persist indefinitely until user interaction.
- **commonActions**: Array of reusable action templates.
  - Each template may include legacy `extensions` patterns (wildcards like `cb?`) and/or rich `filters` (e.g., regex) to decide when the template applies.
  - Files without a source match will try to match these templates using their filters.
  - When a source action uses `{ "type": "common", "name": "Template" }`, it inherits the template's properties and may override specific fields (e.g., `keepOriginal`).
  - Hooks like `isMagazine` can inspect archive contents (e.g., single folder of sequentially numbered images) before allowing the action.
  - You can pass `filters` context to hooks (e.g., `"context": { "allowedNames": ["cover.webp", "credits.png"] }`) to fine-tune behavior.
  - `is3DModel` returns `true` when a supported archive contains at least one common 3D asset file extension (customizable via `context.extensions`).
  - `noSource` filter ensures a common action only runs when the downloaded file had no matching source.
  - When no source matches, Pelagos prompts you to pick a common action filtered to only those whose rules match the file. If the prompt cannot be shown (e.g., headless), it falls back to the best-matching template unless `commonActionsPromptRequired` is set to `true` in the config.

## Supported Actions

### SCP Action
Transfers files to a remote server via SCP.

**Configuration:**
```json
{
    "type": "scp",
    "target": "hostname:/path/to/destination",
    "username": "username",
    "privateKey": "/path/to/private/key",
    "keepOriginal": false,
    "rename": "{{title}}.{{extension}}",
    "overwriteRule": "rename"
}
```

**Options:**
- `target`: Remote destination in format `host:/path`
- `username`: SSH username for authentication
- `privateKey`: Path to SSH private key file
- `keepOriginal`: If `false`, deletes original file after successful transfer
- `rename`: Filename template (supports `{{title}}` and `{{extension}}`)
- `overwriteRule`: How to handle existing files (currently only "rename" supported)

### Dummy Action
Test action that speaks the action name using macOS text-to-speech.

**Configuration:**
```json
{
    "type": "dummy",
    "name": "Test Action"
}
```

## Usage

### Start the Daemon

```bash
launchctl load ~/Library/LaunchAgents/com.pelagos.daemon.plist
```

### Stop the Daemon

```bash
launchctl unload ~/Library/LaunchAgents/com.pelagos.daemon.plist
```

### Check Daemon Status

```bash
launchctl list | grep pelagos
```

### View Logs

Monitor the daemon logs:

```bash
# Main log
tail -f ~/Library/Logs/pelagos.log

# Standard output
tail -f ~/Library/Logs/pelagos.stdout.log

# Standard error
tail -f ~/Library/Logs/pelagos.stderr.log
```

### Manual Testing

You can run the daemon manually for testing:

```bash
cd /path/to/pelagos
./venv/bin/python3 pelagos_daemon.py
# or use the app wrapper
./Pelagos.app/Contents/MacOS/pelagos
```

Press `Ctrl+C` to stop.

## How It Works

1. The daemon watches the Downloads folder for new files
2. When a file is created, it reads the `com.apple.metadata:kMDItemWhereFroms` extended attribute
3. The source URL is extracted and matched against configured sources
4. If a match is found:
   - For `auto: true` actions: executes immediately
   - For `auto: false` actions: shows a banner notification with alerter
5. User clicks notification to execute, or selects from dropdown for multiple actions
6. If no source matches, Pelagos offers matching common actions via notification system
7. A local notification server (port 9999) handles communication between alerter and the daemon

## Notification System

Pelagos uses the **alerter** tool for macOS banner notifications:

- **Banner notifications** appear in the top-right corner
- **Content images** are displayed when available (via `getFeaturedImage` hook)
- **Click-to-execute**: Single actions execute when you click the notification body
- **Dropdown selection**: Multiple actions show a dropdown menu
- **No timeouts**: Notifications persist until you interact with them
- **Local server**: Communication via localhost port 9999

### Notification Behavior

- **Single action**: Click anywhere on the notification to execute
- **Multiple actions**: Click the dropdown to select an action, then Execute
- **Skip option**: Use the close button or "Skip" to ignore the action

## Hooks

- Hook implementations live in `hooks/` and are loaded on demand.
- Each hook module exposes a `register(registry)` function that registers one or more hook callables.
- Common-action filters of type `hook` reference these callables by name and can pass optional `context` data.
- `isMagazine` inspects archives and returns `true` when they contain a single directory of sequentially numbered images. It supports `.zip/.cbz` natively and `.rar/.cbr` when the optional `rarfile` dependency is installed.

### Testing hooks manually

Each hook module can be executed as a script for quick checks:

```bash
# Magazine heuristic (add --allowed-name for extra exceptions)
python hooks/isMagazine ~/Downloads/book.cbz --verbose

# 3D model detection (add --extension for custom formats)
python hooks/is3DModel ~/Downloads/models.zip

# Extension change
python hooks/changeExtension.py test.zip --ext '{"zip": "cbz", "rar": "cbr"}'
```

All commands exit with status 0 on success and print PASS/FAIL diagnostics.

### Available Hooks

#### isMagazine
Detects if an archive contains magazine-style content (single folder with sequentially numbered images).

**Supported formats:**
- `.zip`, `.cbz` (native)
- `.rar`, `.cbr` (requires `rarfile` dependency)

**Configuration:**
```json
{
    "type": "hook",
    "name": "isMagazine",
    "context": {
        "allowedNames": ["cover.webp", "credits.png"],
        "allowedStems": ["title", "toc"]
    }
}
```

**Testing:**
```bash
python hooks/isMagazine.py ~/Downloads/archive.cbz --verbose
```

#### getFeaturedImage
Extracts the first image from an archive to use as a notification content image.

**Supported formats:**
- `.zip`, `.cbz`, `.rar`, `.cbr`

**Configuration:**
```json
{
    "type": "hook",
    "name": "getFeaturedImage"
}
```

**Returns:** Path to extracted image in temp directory

#### is3DModel
Detects if an archive contains 3D model files.

**Supported formats:**
- `.blend`, `.fbx`, `.obj`, `.dae`, `.gltf`, `.glb`, `.3ds`, `.stl`

**Configuration:**
```json
{
    "type": "hook",
    "name": "is3DModel",
    "context": {
        "extensions": [".blend", ".fbx", ".obj"]
    }
}
```

**Testing:**
```bash
python hooks/is3DModel.py ~/Downloads/models.zip
```

#### changeExtension
Changes file extensions during action execution.

**Use case:** Convert `.zip` to `.cbz` or `.rar` to `.cbr` for comic archives.

**Configuration:**
```json
{
    "type": "hook",
    "name": "changeExtension",
    "extensions": {
        "zip": "cbz",
        "rar": "cbr"
    }
}
```

**Testing:**
```bash
python hooks/changeExtension.py test.zip --ext '{"zip": "cbz", "rar": "cbr"}'
```

#### Built-in Filters

##### regex
Matches filenames against a regular expression pattern.

**Configuration:**
```json
{
    "type": "regex",
    "pattern": "^.*\\.(cb.|zip|rar)$",
    "ignoreCase": true
}
```

##### noSource
Ensures the action only runs when the file has no matching source URL.

**Configuration:**
```json
{
    "type": "noSource"
}
```

## Troubleshooting

### Daemon Not Starting

Check the error logs:
```bash
cat ~/Library/Logs/pelagos.stderr.log
```

### Files Not Being Processed

1. Check if the daemon is running: `launchctl list | grep pelagos`
2. Verify the source URL matches your config
3. Check the logs for debug information

### SCP Transfer Failing

1. Verify SSH key authentication works manually
2. Check that the remote path exists
3. Ensure proper permissions on the remote server

## Uninstallation

```bash
# Stop and unload the daemon
launchctl unload ~/Library/LaunchAgents/com.pelagos.daemon.plist

# Remove the plist file
rm ~/Library/LaunchAgents/com.pelagos.daemon.plist

# Optionally remove logs
rm ~/Library/Logs/pelagos*.log
```

## Future Enhancements

- Template-based file renaming
- Additional action types (move, copy, etc.)
- Overwrite rule implementation
- Web UI for configuration
- Multiple destination support
