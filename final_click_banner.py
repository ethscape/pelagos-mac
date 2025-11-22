#!/usr/bin/env python3
import subprocess
import socket
import sys
import time

def send_to_server(message, port=9999):
    """Send message to notification server"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('localhost', port))
        
        # Send message
        sock.send(message.encode('utf-8'))
        
        # Wait for ACK
        ack = sock.recv(1024).decode('utf-8')
        sock.close()
        
        return ack == "ACK"
    except Exception as e:
        print(f"Server communication failed: {e}")
        return False

def show_final_click_banner(title, subtitle, message, port=9999):
    """Show banner notification and wait for actual user click or timeout"""
    
    # Try to send SHOWN
    for attempt in range(3):
        if send_to_server("SHOWN", port):
            break
        time.sleep(0.1)
    
    try:
        # Show banner notification with -execute for reliable click detection
        cmd = [
            '/opt/homebrew/bin/terminal-notifier',
            '-title', title,
            '-subtitle', subtitle,
            '-message', f"{message} - Click this notification to EXECUTE",
            '-sound', 'default',
            '-sender', 'com.pelagos.daemon',
            '-execute', 'echo "clicked" >/tmp/banner_clicked'
        ]
        
        print(f"Launching banner: {' '.join(cmd)}")
        
        # Start banner process
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Banner shown, waiting for user click or timeout...")
        
        # Wait for click file to appear or timeout
        click_file = "/tmp/banner_clicked"
        start_time = time.time()
        timeout_seconds = 10
        
        # Clean up any existing click file
        try:
            os.remove(click_file)
        except:
            pass
        
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
                
                # Wait for process to complete
                try:
                    process.wait(timeout=2)
                except:
                    pass
                
                return
            
            time.sleep(0.5)
        
        # Timeout reached - no click detected
        print("Banner timed out without click - sending SKIP")
        send_to_server("SKIP", port)
        
        # Clean up and kill process
        try:
            if os.path.exists(click_file):
                os.remove(click_file)
        except:
            pass
            
        try:
            process.kill()
            process.wait(timeout=1)
        except:
            pass
            
    except Exception as e:
        print(f"Error showing final click banner: {e}")
        send_to_server("SKIP", port)

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        title = sys.argv[1]
        subtitle = sys.argv[2]
        message = sys.argv[3]
        
        show_final_click_banner(title, subtitle, message)
    else:
        print("Usage: final_click_banner.py <title> <subtitle> <message>")
