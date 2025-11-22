"""isMagazine hook implementation."""

import argparse
import logging
import re
import sys
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple

try:
    import rarfile  # type: ignore
except ImportError:  # pragma: no cover
    rarfile = None

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'
}

DEFAULT_ALLOWED_STEMS = {
    'cover',
    'credits',
    'back',
    'backcover',
    'title',
    'toc',
}

logger = logging.getLogger("pelagos.hooks.isMagazine")


def register(registry):
    registry.register('isMagazine', hook)


def hook(file_path: Path, context: Dict[str, Any] | None = None) -> bool:
    if not file_path.exists():
        logger.debug("Hook isMagazine: file does not exist")
        return False

    allowed_full, allowed_stems = _build_allowed_lists(context)

    suffix = file_path.suffix.lower()

    if suffix in {'.zip', '.cbz'}:
        return _check_zip(file_path, allowed_full, allowed_stems)
    if suffix in {'.rar', '.cbr'}:
        return _check_rar(file_path, allowed_full, allowed_stems)

    logger.debug("Hook isMagazine: unsupported archive type %s", suffix)
    return False


def _build_allowed_lists(context: Dict[str, Any] | None) -> Tuple[Set[str], Set[str]]:
    allowed_full: Set[str] = set()
    allowed_stems: Set[str] = set(DEFAULT_ALLOWED_STEMS)

    if context:
        for name in context.get('allowedNames', []):
            if not isinstance(name, str):
                continue
            lowered = name.lower()
            allowed_full.add(lowered)
            allowed_stems.add(Path(lowered).stem)

    return allowed_full, allowed_stems


def _check_zip(file_path: Path, allowed_full: Set[str], allowed_stems: Set[str]) -> bool:
    if not zipfile.is_zipfile(file_path):
        logger.debug("Hook isMagazine: invalid zip file")
        return False

    with zipfile.ZipFile(file_path) as archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]

    return _validate_entries(entries, allowed_full, allowed_stems)


def _check_rar(file_path: Path, allowed_full: Set[str], allowed_stems: Set[str]) -> bool:
    if rarfile is None:
        logger.debug("Hook isMagazine: rarfile module not available")
        return False

    try:
        with rarfile.RarFile(file_path) as archive:  # type: ignore[attr-defined]
            entries = [info for info in archive.infolist() if not info.isdir()]
    except rarfile.Error as exc:  # type: ignore[attr-defined]
        logger.debug("Hook isMagazine: invalid rar archive %s", exc)
        return False

    return _validate_entries(entries, allowed_full, allowed_stems)


def _validate_entries(entries: List, allowed_full: Set[str], allowed_stems: Set[str]) -> bool:
    if not entries:
        logger.debug("Hook isMagazine: archive has no files")
        return False

    top_level_dirs = set()
    numeric_count = 0
    non_numeric_count = 0
    image_seen = False

    for entry in entries:
        parts = Path(entry.filename).parts
        if len(parts) == 0:
            continue

        if len(parts) == 1:
            top_level_dirs.add("__root__")
        else:
            top_level_dirs.add(parts[0])

        suffix = Path(entry.filename).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            image_seen = True
            path_obj = Path(entry.filename)
            lower_name = path_obj.name.lower()
            lower_stem = path_obj.stem.lower()

            if lower_name in allowed_full or lower_stem in allowed_stems:
                continue

            if _is_numbered_stem(lower_stem):
                numeric_count += 1
            else:
                non_numeric_count += 1

    if len(top_level_dirs) != 1:
        logger.debug("Hook isMagazine: expected single top-level directory, found %s", len(top_level_dirs))
        return False

    if not image_seen:
        logger.debug("Hook isMagazine: no images found")
        return False

    total_considered = numeric_count + non_numeric_count
    if total_considered == 0:
        logger.debug("Hook isMagazine: no numbered images after filtering allowed names")
        return False

    if non_numeric_count / total_considered > 0.2:
        logger.debug(
            "Hook isMagazine: too many non-numeric images (%s of %s)",
            non_numeric_count,
            total_considered,
        )
        return False

    return True


def _is_numbered_stem(stem: str) -> bool:
    digits = ''.join(ch for ch in stem if ch.isdigit())
    return bool(digits)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the isMagazine hook against an archive")
    parser.add_argument("path", type=Path, help="Path to the archive file")
    parser.add_argument(
        "--allowed-name",
        action="append",
        dest="allowed_names",
        default=[],
        help="Additional filename allowed without numbering (can be repeated)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only report PASS/FAIL (suppress debug logs)"
    )

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.quiet else logging.DEBUG)

    context = {}
    if args.allowed_names:
        context["allowedNames"] = args.allowed_names

    result = hook(args.path, context or None)
    if result:
        print(f"PASS: {args.path} looks like a magazine")
        return 0
    print(f"FAIL: {args.path} does not look like a magazine")
    return 1


if __name__ == "__main__":
    sys.exit(main())
