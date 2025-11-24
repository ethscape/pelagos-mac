#!/usr/bin/env python3
"""
Banner notification using alerter
"""
import sys
import os
import time
import subprocess
import socket
import json
from datetime import datetime

# Add the virtual environment to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = script_dir  # alerter_banner.py is in the project root

# Try to find the correct Python version first
import glob
venv_base = os.path.join(project_dir, 'venv', 'lib')
possible_paths = glob.glob(os.path.join(venv_base, 'python*', 'site-packages'))
if possible_paths:
    sys.path.insert(0, possible_paths[0])
    print(f"Using venv path: {possible_paths[0]}")
else:
    print("ERROR: Virtual environment not found")
    sys.exit(1)


def send_to_server(message, port=9999):
    """Send message to notification server"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', port))
        sock.send(message.encode('utf-8'))
        
        # Wait for ACK
        ack = sock.recv(1024).decode('utf-8')
        sock.close()
        
        return ack == "ACK"
    except Exception as e:
        print(f"Error sending to server: {e}")
        return False


def show_alerter_banner(title, subtitle, message, port=9999, action_hash=None, content_image=None, available_actions=None):
    """
    Show banner notification using alerter and wait for user click or timeout.
    
    Args:
        title: Notification title
        subtitle: Notification subtitle
        message: Notification message
        port: Port for notification server communication
        action_hash: Unique hash for this action
        content_image: Path to image file to display
        available_actions: List of available actions (for multiple actions case)
    """
    # Prepare alerter command
    alerter_path = os.path.expanduser("~/.local/bin/alerter")
    if not os.path.exists(alerter_path):
        print("ERROR: alerter not found. Please run install.sh")
        return None
    
    # Build command
    cmd = [
        alerter_path,
        '-title', title,
        '-subtitle', subtitle,
        '-message', message,
        '-sender', 'com.pelagos.daemon',
        '-group', action_hash or 'default',
        '-json'
    ]
    
    # Add content image if provided
    if content_image and os.path.exists(content_image):
        cmd.extend(['-contentImage', content_image])
    
    # Add actions if available (for multiple actions case)
    if available_actions and len(available_actions) > 1:
        # Extract action names
        action_names = [action.get('display_name', action.get('name', 'Unknown')) for action in available_actions]
        actions_string = ','.join(action_names)
        cmd.extend(['-actions', actions_string])
        cmd.extend(['-dropdownLabel', 'Select an action'])
    elif available_actions and len(available_actions) == 1:
        # Single action - use "Execute" as the action button
        cmd.extend(['-actions', 'Execute'])
    else:
        # No actions provided - use "Execute" as default
        cmd.extend(['-actions', 'Execute'])
    
    cmd.extend(['-closeLabel', 'Skip'])
    
    # Record timestamps for fallback
    delivered_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S %z')
    
    try:
        print(f"Banner shown via alerter (hash: {action_hash}), waiting for click or timeout...")
        
        # Run alerter and capture output (no timeout - wait indefinitely for user interaction)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(f"Alerter return code: {result.returncode}")
        print(f"Alerter stdout: {result.stdout}")
        print(f"Alerter stderr: {result.stderr}")
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                # Parse JSON response
                response = json.loads(result.stdout.strip())
                
                # Add source property
                response['source'] = action_hash
                
                print(f"Received response: {json.dumps(response)}")
                
                # Check activation type
                activation_type = response.get('activationType', '')
                
                if activation_type == 'contentsClicked':
                    # User clicked the alert body
                    if available_actions and len(available_actions) == 1:
                        # Single action - confirm execution
                        action_name = available_actions[0].get('display_name', available_actions[0].get('name', 'Unknown'))
                        print(f"User clicked alert body - confirming execution of {action_name}")
                        send_to_server(f"EXECUTE:{action_hash}", port)
                        print(action_hash)  # Print action_hash as the last line for daemon to capture
                        return action_hash
                    else:
                        # Multiple actions - show selection dialog
                        print("User clicked alert body - showing dialog for multiple actions")
                        return None  # Signal to show dialog
                
                elif activation_type == 'actionClicked':
                    # User clicked a specific action
                    activation_value = response.get('activationValue', '')
                    activation_index = response.get('activationValueIndex', '0')
                    
                    if activation_index == '-1':
                        # Error/fallback case
                        print("Alerter failed or was dismissed")
                        return None
                    
                    # Handle multiple actions case
                    if available_actions and len(available_actions) > 1:
                        # User selected from dropdown - send the action name back
                        selected_action_name = activation_value
                        print(f"User selected action from dropdown: {selected_action_name}")
                        send_to_server(f"ACTION:{selected_action_name}:{action_hash}", port)
                        return action_hash
                    else:
                        # Single action - map first action (index 0) to EXECUTE
                        if activation_index == '0':
                            print(f"User selected action: {activation_value}")
                            send_to_server(f"EXECUTE:{action_hash}", port)
                            # For single action, return action_hash to indicate execution
                            # For multiple actions with only Execute button, we need to show dialog
                            if available_actions and len(available_actions) > 1:
                                print("Multiple actions available - need to show dialog for selection")
                                return None  # Signal to show dialog
                            print(action_hash)  # Print action_hash as the last line for daemon to capture
                            return action_hash
                        else:
                            # Other actions could be mapped to different behaviors
                            print(f"User selected alternative action: {activation_value}")
                            return None
                
                elif activation_type == 'closed':
                    # User clicked close button
                    print("User closed notification")
                    send_to_server(f"SKIP:{action_hash}", port)
                    return None
                
                else:
                    # Unknown activation type
                    print(f"Unknown activation type: {activation_type}")
                    return None
                    
            except json.JSONDecodeError as e:
                print(f"Failed to parse alerter response: {e}")
                # Fallback to showing dialog
                return None
        else:
            # Alerter failed or was dismissed
            print("Alerter failed or was dismissed")
            return None
            
    except subprocess.TimeoutExpired:
        print("Alerter timed out")
        return None
    except Exception as e:
        print(f"Error running alerter: {e}")
        return None


def main():
    if len(sys.argv) < 4:
        print("Usage: alerter_banner.py <title> <subtitle> <message> [action_hash] [--content-image path] [--available-actions JSON]")
        sys.exit(1)
    
    title = sys.argv[1]
    subtitle = sys.argv[2]
    message = sys.argv[3]
    action_hash = sys.argv[4] if len(sys.argv) > 4 else None
    content_image = None
    available_actions = None
    
    # Parse arguments
    i = 5
    while i < len(sys.argv):
        if sys.argv[i] == '--content-image' and i + 1 < len(sys.argv):
            content_image = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--available-actions' and i + 1 < len(sys.argv):
            try:
                available_actions = json.loads(sys.argv[i + 1])
            except json.JSONDecodeError:
                print("Invalid JSON for available-actions")
                sys.exit(1)
            i += 2
        else:
            i += 1
    
    result = show_alerter_banner(title, subtitle, message, action_hash=action_hash, content_image=content_image, available_actions=available_actions)
    
    if result:
        print(f"Action executed: {result}")
    else:
        print("No action selected or fallback to dialog")


if __name__ == "__main__":
    main()
