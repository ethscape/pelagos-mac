# Async Action Registry Integration Guide

## Overview
The new hash-based action registry system allows for fully asynchronous notification handling. When a user needs to approve an action, we:

1. Register the action in the registry and get a hash
2. Pass the hash to the notification system
3. User clicks → callback sends `EXECUTE:hash`
4. Daemon retrieves action from registry using hash
5. Execute the action asynchronously

## Components Created

### 1. `action_registry.py`
- **ActionRegistry class**: Manages pending actions with hash-based lookup
- **Methods**:
  - `register_action()`: Store action and return hash
  - `get_action()`: Retrieve action by hash
  - `remove_action()`: Clean up after execution
  - `cleanup_old_actions()`: Remove expired actions

### 2. Updated `click_callback.py`
- Now accepts action hash as second argument
- Sends `EXECUTE:hash` instead of just `EXECUTE`

### 3. Updated `pync_banner.py`
- Accepts `action_hash` parameter
- Passes hash to callback script
- Sends `SHOWN:hash` and `SKIP:hash` messages

### 4. Updated `notify_server.py`
- Parses messages in format `COMMAND:hash`
- Returns full message including hash to caller

## Integration Steps for Daemon

### Step 1: Import the Registry
```python
from action_registry import get_registry
```

### Step 2: Register Action Before Notification

**For single action (Scenario 2):**
```python
def _try_banner_notification(file_path: Path, action: Dict[str, Any]):
    # Register the action
    registry = get_registry()
    action_hash = registry.register_action(
        file_path=file_path,
        action=action,
        action_type='single',
        available_actions=None
    )
    
    # Launch notification with hash
    cmd = [
        venv_python,
        pync_script,
        title,
        subtitle,
        message,
        action_hash  # Pass the hash
    ]
    # ... launch process
```

**For multiple actions (Scenario 1):**
```python
def _try_banner_notification(file_path: Path, available_actions: list):
    # Register with multiple choices
    registry = get_registry()
    action_hash = registry.register_action(
        file_path=file_path,
        action=None,  # No single action yet
        action_type='multiple',
        available_actions=available_actions
    )
    
    # Launch notification with hash
    # ... same as above
```

### Step 3: Handle Response with Hash

```python
# Wait for response
response = notification_server.wait_for_response(timeout=30)

# Parse response
parts = response.split(':', 1)
command = parts[0]
action_hash = parts[1] if len(parts) > 1 else None

if command == "EXECUTE" and action_hash:
    # Retrieve the action from registry
    registry = get_registry()
    action_data = registry.get_action(action_hash)
    
    if action_data:
        if action_data['action_type'] == 'single':
            # Execute the single action
            action = action_data['action']
            # ... execute action
            
        elif action_data['action_type'] == 'multiple':
            # Show dialog to choose from available actions
            available_actions = action_data['available_actions']
            selected_action = _show_action_dialog(file_path, available_actions)
            # ... execute selected action
        
        # Clean up
        registry.remove_action(action_hash)
        
elif command == "SKIP" and action_hash:
    # User skipped - clean up
    registry = get_registry()
    registry.remove_action(action_hash)
```

### Step 4: Periodic Cleanup

Add to daemon main loop:
```python
# Clean up old actions every 5 minutes
if time.time() - last_cleanup > 300:
    registry = get_registry()
    expired = registry.cleanup_old_actions(max_age_seconds=300)
    if expired > 0:
        logger.info(f"Cleaned up {expired} expired actions")
    last_cleanup = time.time()
```

## Benefits

1. **Fully Async**: No blocking waits in daemon
2. **No Race Conditions**: Each action has unique hash
3. **Clean State Management**: Registry handles all pending actions
4. **Automatic Cleanup**: Old actions are removed automatically
5. **Multiple Simultaneous**: Can handle multiple pending actions
6. **Type Safety**: Know if action is single or multiple choice

## Message Protocol

### From Banner to Server:
- `SHOWN:hash` - Notification displayed
- `EXECUTE:hash` - User clicked notification
- `SKIP:hash` - User ignored notification (timeout)

### Response Format:
- `EXECUTE:abc123def456` - Execute action with hash abc123def456
- `SKIP:abc123def456` - Skip action with hash abc123def456
- `TIMEOUT` - No response (legacy, should include hash)

## Next Steps

1. Update `pelagos_daemon.py` to use action registry
2. Modify `_try_banner_notification()` to register actions
3. Update response handling to parse hash and retrieve action
4. Add periodic cleanup to main loop
5. Test with both single and multiple action scenarios
