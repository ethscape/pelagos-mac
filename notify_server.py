#!/usr/bin/env python3
import socket
import threading
import logging

class NotificationServer:
    def __init__(self, port=9999):
        self.port = port
        self.server_socket = None
        self.running = False
        self.current_response = None
        self.response_event = threading.Event()
        
    def start(self):
        """Start the notification server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('localhost', self.port))
        self.server_socket.listen(1)
        self.running = True
        
        logging.info(f"Notification server listening on port {self.port}")
        
        # Start server thread
        server_thread = threading.Thread(target=self._accept_connections, daemon=True)
        server_thread.start()
        
        return server_thread
    
    def _accept_connections(self):
        """Accept incoming connections"""
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, address = self.server_socket.accept()
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client, 
                    args=(client_socket,), 
                    daemon=True
                )
                client_thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"Server error: {e}")
                break
    
    def _handle_client(self, client_socket):
        """Handle client connection"""
        try:
            while self.running:
                data = client_socket.recv(1024).decode('utf-8').strip()
                if not data:
                    break
                
                logging.info(f"Received: {data}")
                
                # Parse message format: COMMAND or COMMAND:action_hash
                parts = data.split(':', 1)
                command = parts[0]
                action_hash = parts[1] if len(parts) > 1 else None
                
                if command == "SHOWN":
                    # Notification was shown successfully
                    if action_hash:
                        logging.info(f"Banner notification shown for action {action_hash}")
                    else:
                        logging.info("Banner notification was shown successfully")
                    
                elif command == "EXECUTE":
                    # User clicked - store full message with hash
                    self.current_response = data  # Store full "EXECUTE:hash" format
                    self.response_event.set()
                    if action_hash:
                        logging.info(f"User response 'EXECUTE' for action {action_hash}")
                        # Remove action from registry immediately to prevent later SKIP
                        try:
                            from action_registry import get_registry
                            registry = get_registry()
                            registry.remove_action(action_hash)
                            logging.info(f"Removed action {action_hash} from registry after EXECUTE")
                        except Exception as e:
                            logging.warning(f"Failed to remove action {action_hash} from registry: {e}")
                    else:
                        logging.info(f"User response received: EXECUTE")
                    break
                elif command == "SKIP":
                    # Skip is just cleanup - don't set response event
                    if action_hash:
                        logging.info(f"User response 'SKIP' for action {action_hash}")
                    else:
                        logging.info(f"User response received: SKIP")
                    # Don't break - continue processing other messages
                elif command in ["DIALOG", "TIMEOUT"]:
                    # These are handled by the daemon timeout logic
                    if action_hash:
                        logging.info(f"User response '{command}' for action {action_hash}")
                    else:
                        logging.info(f"User response received: {command}")
                    # Don't set response event for these - daemon handles timeout
                    
                # Send acknowledgment
                client_socket.send(b"ACK")
                
        except Exception as e:
            logging.error(f"Client handler error: {e}")
        finally:
            client_socket.close()
    
    def wait_for_response(self, timeout=30):
        """Wait for user response"""
        # Clear the event and reset response for each new request
        self.current_response = None
        self.response_event.clear()
        
        if self.response_event.wait(timeout):
            response = self.current_response
            self.current_response = None
            return response
        else:
            return None
    
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()

# Global server instance
notification_server = NotificationServer()
