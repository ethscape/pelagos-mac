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

def show_pync_banner(title, subtitle, message, port=9999):
    """Show banner notification using pync and wait for user click or timeout"""
    
    # Try to send SHOWN
    for attempt in range(3):
        if send_to_server("SHOWN", port):
            break
        time.sleep(0.1)
    
    try:
        # Clean up any existing click file
        click_file = "/tmp/pync_banner_clicked"
        try:
            os.remove(click_file)
        except:
            pass
        
        # Show notification with execute command
        execute_cmd = f'echo "clicked" >{click_file}'
        Notifier.notify(
            f"{message} - Click this notification to EXECUTE",
            title=title,
            subtitle=subtitle,
            sound='default',
            execute=execute_cmd,
            appIcon='/path/to/pelagos/Pelagos.app/Contents/Resources/icon.icns'
        )
        
        print(f"Banner shown via pync, waiting for click or timeout...")
        
        # Wait for click file to appear or timeout
        start_time = time.time()
        timeout_seconds = 10
        
        while time.time() - start_time < timeout_seconds:
            if os.path.exists(click_file):
                # User clicked the banner
                print("User clicked banner - sending EXECUTE")
                send_to_server("EXECUTE", port)
                
                # Clean up click file
                try:
                    os.remove(click_file)
                except:
                    pass
                
                return
            
            time.sleep(0.5)
        
        # Timeout reached - no click detected
        print("Banner timed out without click - sending SKIP")
        send_to_server("SKIP", port)
        
        # Clean up click file
        try:
            if os.path.exists(click_file):
                os.remove(click_file)
        except:
            pass
            
    except Exception as e:
        print(f"Error showing pync banner: {e}")
        send_to_server("SKIP", port)

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        title = sys.argv[1]
        subtitle = sys.argv[2]
        message = sys.argv[3]
        
        show_pync_banner(title, subtitle, message)
    else:
        print("Usage: pync_banner.py <title> <subtitle> <message>")
