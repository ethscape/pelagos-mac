#!/usr/bin/env python3
"""Callback script to send EXECUTE with action hash when notification is clicked"""
import socket
import sys

def send_execute(port=9999, action_hash=None):
    """
    Send EXECUTE command with optional action hash to notification server.
    
    Args:
        port: Server port (default 9999)
        action_hash: Hash of the pending action
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('localhost', port))
        
        # Send EXECUTE with action hash
        if action_hash:
            message = f'EXECUTE:{action_hash}'
        else:
            message = 'EXECUTE'
        
        s.sendall(message.encode('utf-8'))
        s.close()
    except Exception as e:
        print(f"Error sending EXECUTE: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    port = 9999
    action_hash = None
    
    # Parse arguments: port and action_hash
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        action_hash = sys.argv[2]
    
    send_execute(port, action_hash)
