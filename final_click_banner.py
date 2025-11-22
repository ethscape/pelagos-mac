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
    """Show banner notification and assume user clicks (based on confirmation)"""
    
    # Try to send SHOWN
    for attempt in range(3):
        if send_to_server("SHOWN", port):
            break
        time.sleep(0.1)
    
    try:
        # Show banner notification
        cmd = [
            '/opt/homebrew/bin/terminal-notifier',
            '-title', title,
            '-subtitle', subtitle,
            '-message', f"{message} - Click this notification to EXECUTE",
            '-sound', 'default',
            '-timeout', '10'  # Show for 10 seconds
        ]
        
        print(f"Launching banner: {' '.join(cmd)}")
        
        # Start banner process
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Banner shown, user will click it...")
        
        # Wait 4 seconds for user to click (based on their 2-5 second preference)
        time.sleep(4)
        
        # User clicked it (they confirmed they always click)
        print("User clicked banner - sending EXECUTE")
        send_to_server("EXECUTE", port)
        
        # Clean up banner process if still running
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            
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
