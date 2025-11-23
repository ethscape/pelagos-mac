#!/usr/bin/env python3
"""
Action Registry - Manages pending user actions with hash-based lookup
"""
import hashlib
import json
import time
from typing import Dict, Any, Optional
from pathlib import Path

class ActionRegistry:
    """Registry for pending user actions awaiting confirmation"""
    
    def __init__(self):
        self._pending_actions: Dict[str, Dict[str, Any]] = {}
    
    def register_action(self, file_path: Path, action: Dict[str, Any], 
                       action_type: str, available_actions: Optional[list] = None) -> str:
        """
        Register a pending action and return its hash key.
        
        Args:
            file_path: Path to the file being processed
            action: The action dictionary (or None if multiple choices)
            action_type: Either 'single' or 'multiple'
            available_actions: List of available actions (for multiple choice)
        
        Returns:
            Hash key for this pending action
        """
        # Create unique hash based on file path and timestamp
        hash_input = f"{file_path}:{time.time()}".encode('utf-8')
        action_hash = hashlib.sha256(hash_input).hexdigest()[:16]
        
        # Store the pending action
        self._pending_actions[action_hash] = {
            'file_path': str(file_path),
            'action': action,
            'action_type': action_type,
            'available_actions': available_actions,
            'timestamp': time.time()
        }
        
        return action_hash
    
    def get_action(self, action_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a pending action by its hash.
        
        Args:
            action_hash: The hash key for the action
        
        Returns:
            Action data or None if not found
        """
        return self._pending_actions.get(action_hash)
    
    def remove_action(self, action_hash: str) -> bool:
        """
        Remove a pending action from the registry.
        
        Args:
            action_hash: The hash key for the action
        
        Returns:
            True if action was removed, False if not found
        """
        if action_hash in self._pending_actions:
            del self._pending_actions[action_hash]
            return True
        return False
    
    def cleanup_old_actions(self, max_age_seconds: int = 300):
        """
        Remove actions older than max_age_seconds.
        
        Args:
            max_age_seconds: Maximum age in seconds (default 5 minutes)
        """
        current_time = time.time()
        expired_keys = [
            key for key, data in self._pending_actions.items()
            if current_time - data['timestamp'] > max_age_seconds
        ]
        
        for key in expired_keys:
            del self._pending_actions[key]
        
        return len(expired_keys)
    
    def get_pending_count(self) -> int:
        """Get the number of pending actions"""
        return len(self._pending_actions)


# Global registry instance
_registry = None

def get_registry() -> ActionRegistry:
    """Get or create the global action registry"""
    global _registry
    if _registry is None:
        _registry = ActionRegistry()
    return _registry
