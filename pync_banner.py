#!/usr/bin/env python3
"""
Banner notification using pync Python wrapper
"""
import sys
import os
import time
import subprocess
import socket

# Add the virtual environment to Python path
venv_path = '/path/to/pelagos/venv/lib/python3.14/site-packages'
if os.path.exists(venv_path):
    sys.path.insert(0, venv_path)
    print(f"Using venv path: {venv_path}")
else:
    # Try to find the correct Python version
    import glob
    possible_paths = glob.glob('/path/to/pelagos/venv/lib/python*/site-packages')
    if possible_paths:
        sys.path.insert(0, possible_paths[0])
        print(f"Using venv path: {possible_paths[0]}")
    else:
        print("ERROR: Virtual environment not found")
        sys.exit(1)

from pync import Notifier

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
        print(f"Server communication failed: {e}")
        return False

def show_pync_banner(title, subtitle, message, port=9999, action_hash=None):
    """
    Show banner notification using pync and wait for user click or timeout.
    
    Args:
        title: Notification title
        subtitle: Notification subtitle
        message: Notification message
        port: Server port for communication
        action_hash: Hash key for the pending action (optional)
    """
    
    # Try to send SHOWN with action hash
    shown_msg = f"SHOWN:{action_hash}" if action_hash else "SHOWN"
    for attempt in range(3):
        if send_to_server(shown_msg, port):
            break
        time.sleep(0.1)
    
    try:
        # Use a dedicated callback script for click detection
        script_dir = os.path.dirname(os.path.abspath(__file__))
        callback_script = os.path.join(script_dir, 'click_callback.py')
        
        # Get the virtualenv Python to run the callback
        venv_python = sys.executable
        
        # Include action hash in callback command
        if action_hash:
            execute_cmd = f'{venv_python} {callback_script} {port} {action_hash}'
        else:
            execute_cmd = f'{venv_python} {callback_script} {port}'
        
        Notifier.notify(
            f"{message} - Click this notification to EXECUTE",
            title=title,
            subtitle=subtitle,
            sound='default',
            execute=execute_cmd
        )
        
        print(f"Banner shown via pync with Python callback (hash: {action_hash}), waiting for click or timeout...")
        
        # Wait for timeout - if user clicks, the callback will send EXECUTE:hash directly
        start_time = time.time()
        timeout_seconds = 10
        
        while time.time() - start_time < timeout_seconds:
            time.sleep(0.5)
        
        # Timeout reached - no click detected
        # Check if action still exists in registry before sending SKIP
        if action_hash:
            try:
                from action_registry import get_registry
                registry = get_registry()
                action = registry.get_action(action_hash)
                if action:
                    print("Banner timed out without click - sending SKIP")
                    skip_msg = f"SKIP:{action_hash}"
                    send_to_server(skip_msg, port)
                else:
                    print(f"Action {action_hash} already processed - not sending SKIP")
            except Exception as e:
                print(f"Error checking registry: {e}")
                print("Banner timed out - sending SKIP as fallback")
                skip_msg = f"SKIP:{action_hash}"
                send_to_server(skip_msg, port)
        else:
            print("Banner timed out without click - sending SKIP")
            send_to_server("SKIP", port)
            
    except Exception as e:
        print(f"Error showing pync banner: {e}")
        send_to_server("SKIP", port)

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        title = sys.argv[1]
        subtitle = sys.argv[2]
        message = sys.argv[3]
        action_hash = sys.argv[4] if len(sys.argv) > 4 else None
        show_pync_banner(title, subtitle, message, action_hash=action_hash)
    else:
        print("Usage: pync_banner.py <title> <subtitle> <message> [action_hash]")
