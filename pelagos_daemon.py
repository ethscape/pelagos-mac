#!/usr/bin/env python3
"""
Pelagos - Downloads folder monitor daemon for macOS
Monitors Downloads folder and transfers files based on their source URL
"""

import json
import os
import subprocess
import time
import logging
import sys
import fnmatch
import copy
import re
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from urllib.parse import urlparse

from hooks import registry, normalize_hook_result
from action_registry import get_registry

# Configuration
CONFIG_PATH = Path(__file__).parent / "config.json"
DOWNLOADS_FOLDER = Path.home() / "Downloads"
LOG_FILE = Path.home() / "Library/Logs/pelagos.log"
DEFAULT_CONFIRM_TIMEOUT = 120
# Using pync Python wrapper for notifications

# Global notification server for port communication
notification_server = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("pelagos")

def load_config() -> Dict[str, Any]:
    """Load configuration from config.json"""
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            # Provide defaults to avoid KeyErrors later
            config.setdefault('sources', [])
            config.setdefault('commonActions', [])
            config.setdefault('port', 9999)
            return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {
            "sources": [], 
            "commonActions": [],
            "port": 9999
        }


def get_file_source(file_path):
    """Get the 'Where from' metadata from a file using xattr"""
    try:
        # macOS stores the download source in com.apple.metadata:kMDItemWhereFroms
        result = subprocess.run(
            ['xattr', '-p', 'com.apple.metadata:kMDItemWhereFroms', str(file_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # The output is in binary plist format, convert it
            plist_result = subprocess.run(
                ['plutil', '-convert', 'json', '-o', '-', '-'],
                input=result.stdout,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if plist_result.returncode == 0:
                urls = json.loads(plist_result.stdout)
                if urls and len(urls) > 0:
                    return urls[0]  # Return the first URL
        
        return None
    except Exception as e:
        logger.debug(f"Could not get source for {file_path}: {e}")
        return None


def match_source(url: Optional[str], sources: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match a URL against configured sources"""
    if not url:
        return None
    
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    
    for source in sources:
        source_domain = urlparse(source['url']).netloc
        if domain == source_domain or domain.endswith('.' + source_domain):
            return source
    
    return None


def resolve_common_action(action_ref: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve an action reference that points to a common action template"""
    if not action_ref:
        return None

    action_type = action_ref.get('type')
    if action_type != 'common':
        return action_ref

    target_name = action_ref.get('name')
    if not target_name:
        logger.warning("Common action reference missing 'name'")
        return None

    for common_action in config.get('commonActions', []):
        if common_action.get('name') == target_name:
            resolved = copy.deepcopy(common_action)
            # Apply overrides from the reference (excluding type/name metadata)
            for key, value in action_ref.items():
                if key in {'type', 'name'}:
                    continue
                resolved[key] = value
            if 'auto' not in resolved:
                resolved['auto'] = common_action.get('auto', False)
            return resolved

    logger.warning(f"Common action '{target_name}' not found in configuration")
    return None


def _extensions_match(action: Dict[str, Any], file_path: Path) -> bool:
    patterns = action.get('extensions')
    if not patterns:
        return True

    filename = file_path.name.lower()
    extension = file_path.suffix.lower().lstrip('.')

    for pattern in patterns:
        normalized_pattern = pattern.lower()
        if fnmatch.fnmatch(filename, normalized_pattern) or fnmatch.fnmatch(extension, normalized_pattern):
            return True

    return False


def _filters_match(action: Dict[str, Any], file_path: Path, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any]]:
    """Check if filters match. Returns (matches, hook_data)."""
    filters = action.get('filters')
    if not filters:
        return (True, {})

    context = context or {}
    has_source = bool(context.get('has_source'))
    hook_data = {}

    for filter_def in filters:
        filter_type = filter_def.get('type')
        if filter_type == 'regex':
            pattern = filter_def.get('pattern')
            if not pattern:
                logger.warning("Regex filter missing 'pattern'; skipping")
                return (False, hook_data)

            target = filter_def.get('target', 'filename')
            ignore_case = filter_def.get('ignoreCase', True)
            flags = re.IGNORECASE if ignore_case else 0

            try:
                compiled = re.compile(pattern, flags)
            except re.error as err:
                logger.error(f"Invalid regex pattern '{pattern}': {err}")
                return (False, hook_data)

            if target == 'path':
                target_value = str(file_path)
            elif target == 'extension':
                target_value = file_path.suffix
            else:
                target_value = file_path.name

            if not compiled.search(target_value):
                return (False, hook_data)
        elif filter_type == 'hook':
            hook_name = filter_def.get('name')
            if not hook_name:
                logger.warning("Hook filter missing 'name'")
                return (False, hook_data)

            hook_context = filter_def.get('context', {})

            try:
                hook_func = registry.resolve(hook_name)
            except (KeyError, ModuleNotFoundError) as err:
                logger.warning(f"Hook '{hook_name}' could not be resolved: {err}")
                return (False, hook_data)

            try:
                result = hook_func(file_path, hook_context)
                passed, data = normalize_hook_result(result)
                
                # Merge hook data
                if data:
                    hook_data.update(data)
                
                if not passed:
                    return (False, hook_data)
            except Exception as err:
                logger.error(f"Hook '{hook_name}' raised an error for {file_path}: {err}")
                return (False, hook_data)
        elif filter_type == 'noSource':
            if has_source:
                return (False, hook_data)
        else:
            logger.warning(f"Unsupported filter type '{filter_type}' in common action '{action.get('name')}'")
            return (False, hook_data)

    return (True, hook_data)


def action_matches_common_filters(action: Dict[str, Any], file_path: Path, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any]]:
    """Check if action matches filters. Returns (matches, hook_data)."""
    if not _extensions_match(action, file_path):
        return (False, {})
    matches, hook_data = _filters_match(action, file_path, context)
    return (matches, hook_data)


def is_action_auto(action: Dict[str, Any]) -> bool:
    return bool(action.get('auto'))


def find_default_common_action(file_path: Path, config: Dict[str, Any], *, has_source: bool = False) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Find first common action matching the provided file. Returns (action, hook_data)."""
    for common_action in config.get('commonActions', []):
        matches, hook_data = action_matches_common_filters(common_action, file_path, {'has_source': has_source})
        if matches:
            logger.info(f"Matched common action '{common_action.get('name')}' for file {file_path.name} via filters")
            return (copy.deepcopy(common_action), hook_data)

    return (None, {})


def _escape_applescript_string(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def send_notification(title: str, subtitle: Optional[str], message: str) -> None:
    title_escaped = _escape_applescript_string(title)
    message_escaped = _escape_applescript_string(message)
    components = [f'display notification "{message_escaped}" with title "{title_escaped}"']
    if subtitle:
        subtitle_escaped = _escape_applescript_string(subtitle)
        components.append(f'subtitle "{subtitle_escaped}"')
    script = ' '.join(components)

    try:
        subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=10
        )
    except Exception as err:
        logger.debug(f"Failed to send notification: {err}")


def confirm_action_execution(file_path: Path, action: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Confirm action execution with the user.
    
    Attempts banner notification first; falls back to AppleScript dialog if unavailable.
    """
    action_name = action.get('name') or action.get('type', 'action') or "this action"
    target = action.get('target', '')
    message = f"{file_path.name} ➜ {target}" if target else file_path.name

    # Skip confirmation if action is already confirmed (selected from multi-action dialog)
    if action.get('_confirmed'):
        logger.info(f"Action '{action_name}' already confirmed for {file_path.name}")
        return True, "already_confirmed"
    
    # Try banner notification with action registry
    # Extract hook_data if stored in action
    hook_data = action.pop('_hook_data', {})
    action_hash = _try_banner_notification(file_path, action, 'single', hook_data=hook_data, config=config)
    if action_hash:
        # Wait for user response via port communication (only EXECUTE will trigger response)
        logger.info("Waiting for user response via port communication")
        response = notification_server.wait_for_response(timeout=30)
        
        if response:
            # User clicked EXECUTE
            logger.info(f"Received response: {response}")
            parts = response.split(':', 1)
            command = parts[0]
            resp_hash = parts[1] if len(parts) > 1 else None
            
            # Registry already cleaned up by server when EXECUTE was received
            # No need to remove again
            
            if command == "EXECUTE":
                return True, "accepted"
        else:
            # Timeout - user didn't click (or clicked SKIP which doesn't send response)
            logger.warning(f"User confirmation timed out for {file_path.name}")
            
            # Clean up registry
            action_reg = get_registry()
            action_reg.remove_action(action_hash)
            
            return False, "timeout"

    # Banner notification shown but no response received (user ignored)
    logger.info(f"User ignored banner notification for {file_path.name}")
    return False, "user_skip"


def _try_banner_notification(file_path: Path, action: Dict[str, Any], action_type: str = 'single', 
                             available_actions: Optional[list] = None, hook_data: Optional[Dict[str, Any]] = None, 
                             config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Try to show a banner notification using port communication with action registry.
    
    Args:
        hook_data: Additional data from hooks (e.g., contentImage path)
    
    Returns:
        action_hash if notification shown, None if failed
    """
    logger.info("Attempting banner notification via port communication")
    hook_data = hook_data or {}
    
    # Start notification server if not already running
    global notification_server
    if notification_server is None:
        from notify_server import NotificationServer
        # Get port configuration from config
        port = config.get('port', 9999) if config else 9999
        
        notification_server = NotificationServer(port=port)
        notification_server.start()
        time.sleep(0.5)  # Give server time to start
    
    # Register action in registry
    action_reg = get_registry()
    action_hash = action_reg.register_action(
        file_path=file_path,
        action=action,
        action_type=action_type,
        available_actions=available_actions
    )
    
    logger.info(f"Registered action with hash: {action_hash}")
    
    # Prepare notification arguments
    title = "Pelagos"
    subtitle = f"Confirm {action.get('display_name', action['name'])}"
    message = f"File: {file_path.name}"
    
    # Launch alerter banner notification with action hash
    logger.info(f"Launching alerter banner notification (Python wrapper)")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    alerter_banner = os.path.join(script_dir, 'alerter_banner.py')
    
    # Build command with optional content image and available actions
    cmd = [alerter_banner, title, subtitle, message, action_hash]
    if hook_data.get('contentImage'):
        cmd.extend(['--content-image', hook_data['contentImage']])
    if available_actions:
        import json
        cmd.extend(['--available-actions', json.dumps(available_actions)])
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Give process a moment to start and send SHOWN status
    time.sleep(1.0)
    logger.info("Notification client launched successfully")
    
    # Wait for process to complete (alerter is synchronous, unlike pync)
    stdout, stderr = process.communicate()
    
    if process.returncode == 0:
        # Check what alerter actually returned
        logger.info(f"Alerter stdout: {stdout}")
        logger.info(f"Alerter stderr: {stderr}")
        
        # Check if alerter returned None (user clicked body or failed)
        if "No action selected or fallback to dialog" in stdout:
            logger.info("Alerter fallback to dialog - showing AppleScript dialog")
            # For multiple actions, return None so the daemon can show the action selection dialog
            if action_type == 'multiple':
                return None
            # For single actions, user closed/ignored notification - respect that and skip
            logger.info(f"User closed/ignored single-action notification for {file_path.name}")
            return None
        else:
            # Check if alerter returned an action hash (for single actions)
            # The last line of stdout should be the action hash if alerter handled it
            lines = stdout.strip().split('\n')
            if lines:
                # Look for a 16-char hex string at the end (the action hash)
                for line in reversed(lines):
                    line = line.strip()
                    # Check if line is exactly a 16-char hex string
                    if line and len(line) == 16 and all(c in '0123456789abcdef' for c in line.lower()):
                        logger.info(f"Alerter returned action hash: {line}")
                        return line
                    # Check if line contains a 16-char hex string (e.g., "Action executed: hash")
                    import re
                    match = re.search(r'\b([0-9a-f]{16})\b', line.lower())
                    if match:
                        hash_str = match.group(1)
                        logger.info(f"Alerter returned action hash: {hash_str}")
                        return hash_str
            
            # Otherwise, alerter handled the interaction via the notification server
            logger.info("Alerter completed successfully - action already executed via server")
            return None
    else:
        # Alerter failed, fall back to dialog
        logger.info(f"Alerter failed (return code: {process.returncode}), falling back to dialog")
        return _confirm_via_dialog(file_path, action.get('display_name', action['name']), message)


def _confirm_via_dialog(file_path: Path, action_name: str, message: str) -> Tuple[bool, str]:
    """Fallback confirmation via AppleScript dialog."""
    escaped_message = _escape_applescript_string(message)
    escaped_action = _escape_applescript_string(action_name)

    lines = [
        f'set theAction to "{escaped_action}"',
        f'set theMessage to "{escaped_message}"',
        'set theDialogText to "Pelagos needs confirmation to " & theAction & "."',
        'set theButtons to {"Skip", "Execute"}',
        'set theDefault to "Execute"',
        f'set theTimeout to {DEFAULT_CONFIRM_TIMEOUT}',
        'set promptText to theDialogText & return & return & theMessage',
        'set dialogResult to display dialog promptText with title "Pelagos" buttons theButtons default button theDefault giving up after theTimeout',
        'if gave up of dialogResult is true then',
        '    return "GAVE_UP"',
        'else',
        '    return button returned of dialogResult',
        'end if'
    ]

    script = "\n".join(lines)

    try:
        result = subprocess.run(
            ['osascript'],
            input=script,
            capture_output=True,
            text=True,
            timeout=DEFAULT_CONFIRM_TIMEOUT + 5,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"User confirmation timed out for {file_path.name}")
        return False, "timeout"
    except FileNotFoundError:
        logger.error("osascript not available; cannot confirm manual action")
        return False, "error"
    except Exception as err:
        logger.error(f"Failed to prompt for manual action via dialog: {err}")
        return False, "error"

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if result.returncode != 0:
        if stderr or stdout:
            logger.warning(
                "Confirmation dialog failed for %s (exit %s). STDOUT: %s STDERR: %s",
                file_path.name,
                result.returncode,
                stdout or "<empty>",
                stderr or "<empty>",
            )
        else:
            logger.warning(
                "Confirmation dialog failed for %s with exit code %s (no output)",
                file_path.name,
                result.returncode,
            )
        return False, "error"

    selection = stdout.strip().upper()

    if selection == "GAVE_UP" or selection == "":
        logger.warning(f"User confirmation timed out for {file_path.name}")
        return False, "timeout"

    if selection == "EXECUTE":
        return True, "accepted"
    if selection == "SKIP":
        return False, "user_skip"

    logger.warning(
        "Unexpected confirmation response '%s' for %s (STDERR: %s)",
        stdout,
        file_path.name,
        stderr or "<empty>",
    )
    return False, "error"


def prompt_user_for_common_action(file_path: Path, config: Dict[str, Any], default_action_name: Optional[str] = None, *, has_source: bool = False) -> Optional[Dict[str, Any]]:
    """Prompt the user to choose a common action to apply"""
    actions = config.get('commonActions', [])
    if not actions:
        return None

    # Collect actions and their hook data
    filtered_actions_with_data = []
    for action in actions:
        if action.get('name'):
            matches, hook_data = action_matches_common_filters(action, file_path, {'has_source': has_source})
            if matches:
                filtered_actions_with_data.append((action, hook_data))
    
    filtered_actions = [action for action, _ in filtered_actions_with_data]

    if not filtered_actions:
        logger.info(f"No common action templates matched filters for {file_path.name}")
        return None

    if len(filtered_actions_with_data) == 1:
        single_action, hook_data = filtered_actions_with_data[0]
        name = single_action.get('name') or single_action.get('type', 'action')
        target = single_action.get('target', '')
        message = f"{file_path.name} ➜ {target}" if target else file_path.name
        logger.info(
            f"Single common action match '{name}' detected for {file_path.name}; using banner notification"
        )
        
        # Use banner notification with action registry
        # Pass the single action as available_actions for proper handling
        action_hash = _try_banner_notification(file_path, single_action, 'single', 
                                              available_actions=[single_action], 
                                              hook_data=hook_data, config=config)
        if action_hash is None:
            # User closed/ignored notification - fall through to show all matching actions
            # Get ALL actions that match the file extension (not just filtered ones)
            file_ext = file_path.suffix.lstrip('.').lower()
            all_matching_actions = [a for a in actions if file_ext in [ext.lower() for ext in a.get('extensions', [])]]
            if len(all_matching_actions) > 1:
                # Show all matching actions in dialog
                logger.info(f"User closed single-action notification - showing all {len(all_matching_actions)} matching actions")
                # Update filtered_actions to include all matching actions
                filtered_actions = all_matching_actions
                # Continue to multiple actions section below
            else:
                # Only one action total, user closed it - skip
                logger.info(f"User closed single-action notification for {file_path.name}")
                return {'_user_skipped': True}
        elif action_hash:
            # If action_hash is returned, it means alerter already handled the user interaction
            # and the user clicked Execute. The action should be executed immediately.
            if isinstance(action_hash, str) and len(action_hash) == 16:
                # alerter_banner.py returned the action hash, meaning user clicked Execute
                logger.info(f"User executed action via alerter for {file_path.name}")
                action = copy.deepcopy(single_action)
                action['_manual_selection'] = True  # Mark as manually confirmed
                action['_hook_data'] = hook_data  # Preserve hook data
                return action
            else:
                # Wait for response (only EXECUTE will trigger response)
                response = notification_server.wait_for_response(timeout=None)
                
                if response:
                    # User clicked EXECUTE
                    parts = response.split(':', 1)
                    command = parts[0]
                    resp_hash = parts[1] if len(parts) > 1 else None
                    
                    # Registry already cleaned up by server when EXECUTE was received
                    
                    if command == "EXECUTE":
                        action = copy.deepcopy(single_action)
                        action['_manual_selection'] = True  # Mark as manually confirmed
                        action['_hook_data'] = hook_data  # Preserve hook data
                        return action
                else:
                    # No response - user closed notification
                    # Clean up registry
                    action_reg = get_registry()
                    action_reg.remove_action(action_hash)
                    
                    # User ignored notification - skip
                    logger.info(f"User ignored banner notification for {file_path.name}")
                    return {'_user_skipped': True}

    # Multiple actions: show banner notification first, then dialog if clicked
    action_name_map = {action.get('name'): action for action in filtered_actions if action.get('name')}
    if not action_name_map:
        return None

    # Show banner notification for multiple actions
    logger.info(f"Multiple common action matches detected for {file_path.name}; using banner notification first")
    
    # Create a dummy action for banner notification
    banner_action = {
        'name': 'Multiple Actions Available',
        'type': 'banner',
        'target': f"{len(filtered_actions)} actions available"
    }
    
    # Try banner notification with action registry
    # For multiple actions, use hook_data from first matching action
    first_hook_data = filtered_actions_with_data[0][1] if filtered_actions_with_data else {}
    action_hash = _try_banner_notification(file_path, banner_action, 'multiple', available_actions=filtered_actions, hook_data=first_hook_data, config=config)
    if action_hash is None:
        # User clicked alert body or alerter failed - show action selection dialog
        logger.info(f"User clicked alert body for {file_path.name} - showing action selection dialog")
        # Create AppleScript list items
        action_names = list(action_name_map.keys())
        prompt_text = _escape_applescript_string(f"Pelagos detected {file_path.name}. Choose a common action or Skip.")
        
        # Use the exact same pattern as the working code
        action_list_str = ", ".join(f'"{_escape_applescript_string(name)}"' for name in action_name_map.keys())
        
        # Use choose from list for all actions
        action_list = list(action_name_map.keys())
        
        # Build the action list for AppleScript
        action_items = ", ".join([f'"{_escape_applescript_string(name)}"' for name in action_list])
        
        script = f'''set actionList to {{{action_items}}}
set userSelection to choose from list actionList with prompt "{prompt_text}" default items (item 1 of actionList)
if userSelection is false then
    return "Skip"
else
    return item 1 of userSelection as text
end if'''
        
        logger.info(f"AppleScript to execute: {script}")
        
        try:
            logger.info(f"Executing AppleScript...")
            # Use -e flag to pass script directly
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True
            )
            
            logger.info(f"osascript return code: {result.returncode}")
            logger.info(f"osascript stdout: {result.stdout.strip()}")
            logger.info(f"osascript stderr: {result.stderr.strip()}")
            
            if result.returncode != 0:
                logger.error(f"osascript returned error: {result.stderr.strip()}")
                return None
            
            selection = result.stdout.strip()
            
            if selection == 'Skip' or not selection:
                logger.info(f"User skipped common action for {file_path.name}")
                return {'_user_skipped': True}
            
            # Find the action by name
            if selection in action_name_map:
                selected_action = action_name_map[selection]
                logger.info(f"User selected common action '{selection}' for {file_path.name}")
                # Return a copy with manual_selection flag
                action_copy = copy.deepcopy(selected_action)
                action_copy['_manual_selection'] = True
                return action_copy
            else:
                logger.error(f"Selected action '{selection}' not found in action map")
                return None
        except FileNotFoundError:
            logger.error("osascript not found; cannot prompt for common action")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Timed out waiting for user selection for {file_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to prompt for common action: {e}")
            return None
    
    if action_hash:
        # If action_hash is returned as a string (16 chars), it means alerter already handled the interaction
        # We need to wait for the response that the server has already received
        if isinstance(action_hash, str) and len(action_hash) == 16:
            # Check if there's already a response (server might have already received it from alerter)
            # Don't clear the response - check if it's already set
            if notification_server.response_event.is_set():
                # Response is already available
                response = notification_server.current_response
                logger.info(f"Banner response already available: {response}")
                # Clear it after reading
                notification_server.current_response = None
                notification_server.response_event.clear()
            else:
                # Wait for response (in case it hasn't been received yet)
                response = notification_server._wait_for_response_no_clear(timeout=5)
                logger.info(f"Banner response received: {response}")
            if response:  # User responded to banner
                parts = response.split(':', 2)
                command = parts[0]
                
                if command == 'ACTION' and len(parts) >= 3:
                    # User selected action from alerter dropdown
                    selected_action_name = parts[1]
                    resp_hash = parts[2] if len(parts) > 2 else None
                    
                    # Find the selected action
                    selected_action = action_name_map.get(selected_action_name)
                    if selected_action:
                        logger.info(f"User selected action '{selected_action_name}' from alerter")
                        selected_action['_manual_selection'] = True
                        return copy.deepcopy(selected_action)
                    else:
                        logger.warning(f"User selected unknown common action '{selected_action_name}'")
                        return None
                elif command == 'EXECUTE':
                    # User clicked Execute button - show dialog for action selection
                    logger.info("User clicked Execute for multiple actions - showing dialog")
                    action_list_str = ", ".join(f'"{_escape_applescript_string(name)}"' for name in action_name_map.keys())
                    prompt_text = _escape_applescript_string(f"Pelagos detected '{file_path.name}'. Choose a common action or Skip.")
                    
                    script_lines = [
                        f'set actionList to {{{action_list_str}}}',
                        f'set promptText to "{prompt_text}"',
                        'set selection to choose from list actionList with prompt promptText default items {item 1 of actionList}',
                        'if selection is false then return "SKIP"',
                        'return item 1 of selection'
                    ]
                    script = 'osascript -e "' + '" -e "'.join(script_lines) + '"'
                    
                    try:
                        result = subprocess.run(
                            script,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        
                        if result.returncode != 0:
                            logger.error(f"osascript returned error: {result.stderr.strip()}")
                            return None
                        
                        selection = result.stdout.strip()
                        
                        if not selection or selection == 'SKIP' or selection.lower() == 'false':
                            logger.info(f"User skipped common action for {file_path.name}")
                            return {'_user_skipped': True}
                        
                        selected_action = action_name_map.get(selection)
                        if not selected_action:
                            logger.warning(f"User selected unknown common action '{selection}'")
                            return None
                        
                        logger.info(f"User selected common action '{selection}' for {file_path.name}")
                        selected_action = copy.deepcopy(selected_action)
                        selected_action['_manual_selection'] = True
                        return selected_action
                        
                    except FileNotFoundError:
                        logger.error("osascript not found - cannot show dialog")
                        return None
                    except subprocess.TimeoutExpired:
                        logger.warning(f"User confirmation timed out for {file_path.name}")
                        return None
                    except Exception as e:
                        logger.error(f"Error showing action selection dialog: {e}")
                        return None
        else:
            # Wait for response (only EXECUTE will trigger response)
            response = notification_server.wait_for_response(timeout=30)
            
            logger.info(f"Banner response received: {response}")
            if response:  # User responded to banner
                parts = response.split(':', 2)
                command = parts[0]
                
                if command == 'ACTION' and len(parts) >= 3:
                    # User selected action from alerter dropdown
                    selected_action_name = parts[1]
                    resp_hash = parts[2] if len(parts) > 2 else None
                    
                    # Find the selected action
                    selected_action = action_name_map.get(selected_action_name)
                    if selected_action:
                        logger.info(f"User selected action '{selected_action_name}' from alerter")
                        selected_action['_manual_selection'] = True
                        return copy.deepcopy(selected_action)
                    else:
                        logger.warning(f"User selected unknown common action '{selected_action_name}'")
                        return None
                elif command == 'EXECUTE':
                    # User clicked EXECUTE
                    resp_hash = parts[1] if len(parts) > 1 else None
                    
                    # If there's only one action, execute it directly
                    if len(action_name_map) == 1:
                        selected_action_name = list(action_name_map.keys())[0]
                        selected_action = action_name_map[selected_action_name]
                        logger.info(f"Single action '{selected_action_name}' executed via EXECUTE")
                        selected_action['_manual_selection'] = True
                        # Preserve hook_data from first matching action
                        selected_action['_hook_data'] = first_hook_data
                        return copy.deepcopy(selected_action)
                    
                    # Otherwise show dialog with action options (backward compatibility)
                    action_list_str = ", ".join(f'"{_escape_applescript_string(name)}"' for name in action_name_map.keys())
                    prompt_text = _escape_applescript_string(f"Pelagos detected '{file_path.name}'. Choose a common action or Skip.")

                    script_lines = [
                        f'set actionList to {{{action_list_str}}}',
                        f'set promptText to "{prompt_text}"',
                        'set selection to choose from list actionList with prompt promptText default items {item 1 of actionList}',
                        'if selection is false then return "SKIP"',
                        'return item 1 of selection'
                    ]
                    
                    script = "\n".join(script_lines)

                    try:
                        result = subprocess.run(
                            ['osascript'],
                            input=script,
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        
                        if result.returncode != 0:
                            logger.error(f"osascript returned error: {result.stderr.strip()}")
                            return None

                        selection = result.stdout.strip()
                        
                        # Registry already cleaned up by server when EXECUTE was received
                        
                        if not selection or selection == 'SKIP' or selection.lower() == 'false':
                            logger.info(f"User skipped common action for {file_path.name}")
                            return {'_user_skipped': True}  # Special marker for intentional skip

                        selected_action = action_name_map.get(selection)
                        if not selected_action:
                            logger.warning(f"User selected unknown common action '{selection}'")
                            return None

                        logger.info(f"User selected common action '{selection}' for {file_path.name}")
                        selected_action = copy.deepcopy(selected_action)
                        selected_action['_confirmed'] = True  # Mark as already confirmed
                        selected_action['_manual_selection'] = True  # Mark as manually confirmed
                        # Preserve hook_data from first matching action
                        selected_action['_hook_data'] = first_hook_data
                        return selected_action
                        
                    except FileNotFoundError:
                        logger.error("osascript not found; cannot prompt for common action")
                        return None
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Timed out waiting for user selection for {file_path}")
                        return None
                    except Exception as e:
                        logger.error(f"Failed to prompt for common action: {e}")
                        return None
            
            # If we get here, there was no response or it was invalid
            logger.info(f"User ignored banner notification for {file_path.name}")
            return {'_user_skipped': True}  # Special marker for intentional skip


def execute_scp_action(file_path, action: Dict[str, Any]):
    """Execute SCP action to transfer file"""
    try:
        file_path = Path(file_path)
        
        # Check for extension change in hook data
        hook_data = action.pop('_hook_data', {})
        new_extension = hook_data.get('new_extension')
        
        # Build the filename
        if action.get('rename'):
            # For now, use the original filename (template support can be added later)
            filename = file_path.name
        else:
            filename = file_path.name
        
        # Apply extension change if needed
        if new_extension:
            file_path_obj = Path(filename)
            filename = f"{file_path_obj.stem}.{new_extension}"
            logger.info(f"Changed extension from {file_path_obj.suffix} to .{new_extension}")
        
        # Build SCP command
        target = action['target']
        remote_path = f"{target}/{filename}"
        
        # Use private key if specified
        scp_cmd = ['scp']
        if action.get('privateKey'):
            scp_cmd.extend(['-i', action['privateKey']])
        
        scp_cmd.extend([str(file_path), remote_path])
        
        logger.info(f"Transferring {file_path.name} to {remote_path}")
        
        # Execute SCP
        result = subprocess.run(
            scp_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully transferred {file_path.name}")
            
            # Handle keepOriginal setting
            if not action.get('keepOriginal', False):
                try:
                    file_path.unlink()
                    logger.info(f"Deleted original file: {file_path.name}")
                except Exception as e:
                    logger.error(f"Failed to delete original file: {e}")
            
            return True
        else:
            logger.error(f"SCP failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"SCP timeout for {file_path}")
        return False
    except Exception as e:
        logger.error(f"Error executing SCP action: {e}")
        return False


def process_file(file_path, config: Dict[str, Any]):
    """Process a file: check source and execute action"""
    import traceback
    try:
        logger.info(f"=== START PROCESSING FILE: {file_path} (CALLER: {traceback.format_stack()[-2].strip()}) ===")
        # Wait a bit to ensure file is fully written
        time.sleep(2)
        
        # Check if file still exists (might have been moved/deleted)
        if not os.path.exists(file_path):
            logger.debug(f"File no longer exists: {file_path}")
            return
        
        # Skip directories
        if os.path.isdir(file_path):
            return

        path_obj = Path(file_path)

        # Get the source URL
        source_url = get_file_source(file_path)
        if source_url:
            logger.info(f"File: {path_obj.name}, Source: {source_url}")
            matched_source = match_source(source_url, config.get('sources', []))
        else:
            logger.info(f"File: {path_obj.name}, Source: <unknown>")
            matched_source = None

        action = None

        if matched_source:
            logger.info(f"Matched source: {matched_source['name']}")
            action = resolve_common_action(matched_source.get('action'), config)
            has_source = True
        else:
            has_source = False
            default_common, hook_data = find_default_common_action(path_obj, config, has_source=has_source)
            default_name = default_common.get('name') if default_common else None

            if default_common and is_action_auto(default_common):
                logger.info(f"Auto-executing common action '{default_name}' for {path_obj.name}")
                action = default_common
                # Store hook_data for later use
                if hook_data:
                    action['_hook_data'] = hook_data
            elif config.get('commonActions'):
                logger.debug(f"No source matched for {file_path}. Prompting user for common action selection.")
                action = prompt_user_for_common_action(path_obj, config, default_action_name=default_name, has_source=has_source)
                if not action:
                    # Action was already executed via alerter banner notification
                    logger.info(f"Action already executed via alerter for {path_obj.name}")
                    return
                elif action == "MANUAL_EXECUTE":
                    # This shouldn't happen anymore, but keep for backward compatibility
                    logger.info(f"Received MANUAL_EXECUTE marker - using default action '{default_name}' for {path_obj.name} (executed via alerter)")
                    action = copy.deepcopy(default_common)
                    action['_manual_selection'] = True
                    if hook_data:
                        action['_hook_data'] = hook_data
                elif isinstance(action, dict) and action.get('_user_skipped'):
                    if default_common and not config.get('commonActionsPromptRequired'):
                        # If prompt failed (e.g., headless), fall back to default match
                        logger.info(f"Falling back to default common action '{default_name}' for {path_obj.name}")
                        action = copy.deepcopy(default_common)
                    else:
                        logger.info(f"No common action selected for {path_obj.name}")
                        return
                elif isinstance(action, dict) and action.get('_user_skipped'):
                    # User intentionally skipped the action selection
                    logger.info(f"User intentionally skipped action selection for {path_obj.name}")
                    return
            else:
                logger.debug(f"No matching source and no common actions defined for {file_path}")
                return

        if not action:
            # Action was already executed via alerter banner notification
            logger.info(f"Action already executed via alerter for {path_obj.name}")
            return

        manual_selection = bool(action.pop('_manual_selection', False))

        logger.info(f"Action: {action}, manual_selection: {manual_selection}, is_auto: {is_action_auto(action) if action else 'N/A'}")

        if not is_action_auto(action) and not manual_selection:
            confirmed, reason = confirm_action_execution(path_obj, action, config)
            if not confirmed:
                log_message = f"Action skipped for {path_obj.name} (reason: {reason})"
                if reason == "user_skip":
                    logger.info(log_message)
                else:
                    logger.warning(log_message)
                return

        action_type = action.get('type')
        if action_type == 'scp':
            execute_scp_action(file_path, action)
        elif action_type == 'dummy':
            action_name = action.get('name', 'Unknown')
            logger.info(f"Dummy action '{action_name}' executed for {path_obj.name}")
            try:
                subprocess.run(['say', f"Executed {action_name} action for {path_obj.name}"], check=True, capture_output=True)
                logger.info(f"Spoke action name: {action_name}")
            except Exception as e:
                logger.warning(f"Failed to speak action name: {e}")
        
        logger.info(f"=== END PROCESSING FILE: {file_path} (SUCCESS) ===")
            
    except Exception as err:
        logger.error(f"Error processing file {file_path}: {err}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.info(f"=== END PROCESSING FILE: {file_path} (ERROR) ===")
        return


class DownloadsHandler(FileSystemEventHandler):
    """Handler for file system events in Downloads folder"""
    
    def __init__(self, config):
        self.config = config
        self.processed_files = set()
    
    def on_created(self, event):
        """Handle file creation events"""
        self._handle_file_event(event)
    
    def on_modified(self, event):
        """Handle file modification events"""
        # Only process if it's a new file that hasn't been processed yet
        # (some systems fire both created and modified for new files)
        self._handle_file_event(event)
    
    def _handle_file_event(self, event):
        """Common file event handling"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        
        # Avoid processing the same file multiple times
        if file_path in self.processed_files:
            logger.info(f"Skipping already processed file: {file_path}")
            return
        
        logger.info(f"Processing new file: {file_path} (event: {event.event_type})")
        self.processed_files.add(file_path)
        
        # Process the file in a separate thread to allow concurrent processing
        import threading
        thread = threading.Thread(target=process_file, args=(file_path, self.config), daemon=True)
        thread.start()
        
        # Clean up processed files set to avoid memory leak
        if len(self.processed_files) > 1000:
            self.processed_files.clear()


def check_single_instance():
    """Ensure only one daemon instance is running"""
    import psutil
    import sys
    import copy
    
    current_pid = os.getpid()
    current_script = os.path.abspath(__file__)
    
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] == current_pid:
                    continue
                    
                cmdline = proc.info.get('cmdline', [])
                if cmdline and any(current_script in str(arg) for arg in cmdline):
                    logger.warning(f"Another daemon instance found (PID {proc.info['pid']}), stopping it")
                    proc.terminate()
                    proc.wait(timeout=5)
                    logger.info(f"Stopped duplicate daemon instance (PID {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except ImportError:
        # Fallback if psutil not available
        logger.warning("psutil not available, cannot check for duplicate instances")
        return

def main():
    """Main daemon loop"""
    # Ensure single instance
    check_single_instance()
    
    logger.info("Starting Pelagos daemon")
    logger.info(f"Monitoring folder: {DOWNLOADS_FOLDER}")
    logger.info(f"Config file: {CONFIG_PATH}")
    
    # Load configuration
    config = load_config()
    logger.info(f"Loaded {len(config.get('sources', []))} source(s)")
    
    # Create observer
    event_handler = DownloadsHandler(config)
    observer = Observer()
    observer.schedule(event_handler, str(DOWNLOADS_FOLDER), recursive=False)
    
    # Start monitoring
    observer.start()
    logger.info("Daemon started successfully")
    
    try:
        while True:
            time.sleep(60)
            # Reload config periodically to pick up changes
            config = load_config()
            event_handler.config = config
    except KeyboardInterrupt:
        logger.info("Stopping daemon")
        observer.stop()
    
    observer.join()
    logger.info("Daemon stopped")


if __name__ == "__main__":
    main()
