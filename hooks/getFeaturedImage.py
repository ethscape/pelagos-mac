"""getFeaturedImage hook implementation.

This hook extracts the featured/first image from a compressed archive file
and saves it to /tmp for use as a notification content image.
"""

import argparse
import logging
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, Any, Tuple

try:
    import rarfile  # type: ignore
except ImportError:  # pragma: no cover
    rarfile = None

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'
}

logger = logging.getLogger("pelagos.hooks.getFeaturedImage")


def register(registry):
    registry.register('getFeaturedImage', hook)


def _cleanup_old_images(temp_dir: Path, max_age_hours: int = 24) -> None:
    """Clean up extracted images older than max_age_hours."""
    try:
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for image_path in temp_dir.glob("*"):
            if image_path.is_file():
                file_age = current_time - image_path.stat().st_mtime
                if file_age > max_age_seconds:
                    image_path.unlink()
                    logger.debug(f"Hook getFeaturedImage: cleaned up old image {image_path}")
    except Exception as e:
        logger.debug(f"Hook getFeaturedImage: cleanup error: {e}")


def hook(file_path: Path, context: Dict[str, Any] | None = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Extract the featured image from an archive.
    
    Returns:
        (True, {'contentImage': path_to_extracted_image}) on success
        (True, {}) if no suitable image found (doesn't fail the action)
    """
    if not file_path.exists():
        logger.debug("Hook getFeaturedImage: file does not exist")
        return (True, {})  # Don't fail the action

    suffix = file_path.suffix.lower()
    
    # Clean up old images before extracting new ones
    temp_dir = Path(tempfile.gettempdir()) / "pelagos_images"
    if temp_dir.exists():
        _cleanup_old_images(temp_dir)

    try:
        if suffix in {'.zip', '.cbz'}:
            image_path = _extract_from_zip(file_path)
        elif suffix in {'.rar', '.cbr'}:
            image_path = _extract_from_rar(file_path)
        else:
            logger.debug("Hook getFeaturedImage: unsupported archive type %s", suffix)
            return (True, {})
        
        if image_path:
            return (True, {'contentImage': str(image_path)})
        return (True, {})
    
    except Exception as e:
        logger.error(f"Hook getFeaturedImage: error extracting image: {e}")
        return (True, {})  # Don't fail the action on error


def _extract_from_zip(file_path: Path) -> Path | None:
    """Extract the first image from a ZIP archive."""
    if not zipfile.is_zipfile(file_path):
        logger.debug("Hook getFeaturedImage: invalid zip file")
        return None

    try:
        with zipfile.ZipFile(file_path) as archive:
            # Get all image files, sorted by name
            image_files = sorted([
                info for info in archive.infolist()
                if not info.is_dir() and Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
            ], key=lambda x: x.filename)
            
            if not image_files:
                logger.debug("Hook getFeaturedImage: no images found in zip")
                return None
            
            # Extract the first image to temp directory
            first_image = image_files[0]
            temp_dir = Path(tempfile.gettempdir()) / "pelagos_images"
            temp_dir.mkdir(exist_ok=True)
            
            # Create a safe filename
            safe_name = Path(first_image.filename).name
            output_path = temp_dir / f"{file_path.stem}_{safe_name}"
            
            # Extract the file
            with archive.open(first_image) as source:
                with open(output_path, 'wb') as dest:
                    dest.write(source.read())
            
            logger.info(f"Hook getFeaturedImage: extracted {first_image.filename} to {output_path}")
            return output_path
    
    except Exception as e:
        logger.error(f"Hook getFeaturedImage: error extracting from zip: {e}")
        return None


def _extract_from_rar(file_path: Path) -> Path | None:
    """Extract the first image from a RAR archive."""
    if rarfile is None:
        logger.debug("Hook getFeaturedImage: rarfile module not available")
        return None

    try:
        with rarfile.RarFile(file_path) as archive:  # type: ignore[attr-defined]
            # Get all image files, sorted by name
            image_files = sorted([
                info for info in archive.infolist()
                if not info.isdir() and Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
            ], key=lambda x: x.filename)
            
            if not image_files:
                logger.debug("Hook getFeaturedImage: no images found in rar")
                return None
            
            # Extract the first image to temp directory
            first_image = image_files[0]
            temp_dir = Path(tempfile.gettempdir()) / "pelagos_images"
            temp_dir.mkdir(exist_ok=True)
            
            # Create a safe filename
            safe_name = Path(first_image.filename).name
            output_path = temp_dir / f"{file_path.stem}_{safe_name}"
            
            # Extract the file
            with archive.open(first_image) as source:  # type: ignore[attr-defined]
                with open(output_path, 'wb') as dest:
                    dest.write(source.read())
            
            logger.info(f"Hook getFeaturedImage: extracted {first_image.filename} to {output_path}")
            return output_path
    
    except Exception as e:
        logger.error(f"Hook getFeaturedImage: error extracting from rar: {e}")
        return None


def main(argv: list[str] | None = None) -> int:
    """Test the getFeaturedImage hook against an archive"""
    parser = argparse.ArgumentParser(description="Test the getFeaturedImage hook against an archive")
    parser.add_argument("path", type=Path, help="Path to the archive file")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only report PASS/FAIL (suppress debug logs)"
    )

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.quiet else logging.DEBUG)

    result = hook(args.path, {})
    passed, data = result
    
    if passed:
        if data.get('contentImage'):
            print(f"PASS: Extracted featured image to {data['contentImage']}")
        else:
            print(f"PASS: No suitable image found in {args.path}")
        return 0
    else:
        print(f"FAIL: Hook failed for {args.path}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
