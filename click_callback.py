#!/usr/bin/env python3
"""Callback script to send EXECUTE with action hash when notification is clicked"""
import socket
import sys

def send_execute(port=None, action_hash=None):
    """Send EXECUTE command to notification server"""
    if port is None:
        # Get the actual port from the notification server
        try:
            from notify_server import notification_server
            port = notification_server.get_port()
        except ImportError:
            port = 9999  # Fallback to default port
    
    message = f"EXECUTE:{action_hash}" if action_hash else "EXECUTE"
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # 5 second timeout
        sock.connect(('localhost', port))
        sock.send(message.encode('utf-8'))
        
        # Wait for acknowledgment
        ack = sock.recv(1024).decode('utf-8')
        sock.close()
        
        if ack == "ACK":
            return True
        else:
            print(f"Unexpected acknowledgment: {ack}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Error sending to server: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    port = None  # Auto-detect port
    action_hash = None
    
    # Parse arguments: port and action_hash
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            # If first arg is not a port, treat it as action_hash
            action_hash = sys.argv[1]
    if len(sys.argv) > 2:
        action_hash = sys.argv[2]
    
    send_execute(port, action_hash)
