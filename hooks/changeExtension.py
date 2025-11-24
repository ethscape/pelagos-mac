"""changeExtension hook implementation."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

logger = logging.getLogger("pelagos.hooks.changeExtension")


def register(registry):
    registry.register('changeExtension', hook)


def hook(file_path: Path, context: Dict[str, Any] | None = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Hook to change file extension based on mapping.
    
    This hook always returns True (passes the filter) but adds data to change
    the file extension during the action execution.
    
    Args:
        file_path: The file to check
        context: Hook context containing the extension mapping
        
    Returns:
        Tuple of (True, data) where data contains the new extension
    """
    if not context:
        logger.debug("Hook changeExtension: no context provided")
        return (True, {})
    
    extensions = context.get('extensions', {})
    if not extensions:
        logger.debug("Hook changeExtension: no extensions mapping provided")
        return (True, {})
    
    current_ext = file_path.suffix.lstrip('.').lower()
    new_ext = extensions.get(current_ext)
    
    if new_ext:
        logger.info(f"Hook changeExtension: mapping {current_ext} -> {new_ext}")
        return (True, {'new_extension': new_ext})
    
    logger.debug(f"Hook changeExtension: no mapping for {current_ext}")
    return (True, {})


def main():
    """Test the changeExtension hook against a file."""
    parser = argparse.ArgumentParser(description="Test the changeExtension hook against a file")
    parser.add_argument("file", help="File to test against")
    parser.add_argument("--ext", help="Extension mapping as JSON string", 
                       default='{"zip": "cbz", "rar": "cbr"}')
    parser.add_argument("-q", "--quiet", action="store_true", help="Only show pass/fail")
    
    args = parser.parse_args()
    
    import json
    try:
        extensions = json.loads(args.ext)
    except json.JSONDecodeError as e:
        print(f"Error parsing extensions JSON: {e}")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO if args.quiet else logging.DEBUG)
    
    file_path = Path(args.file)
    context = {'extensions': extensions}
    
    passed, data = hook(file_path, context)
    
    if args.quiet:
        print("PASS" if passed else "FAIL")
    else:
        print(f"File: {file_path}")
        print(f"Current extension: {file_path.suffix}")
        if data.get('new_extension'):
            print(f"New extension: {data['new_extension']}")
        print(f"Result: {'PASS' if passed else 'FAIL'}")


if __name__ == "__main__":
    main()
