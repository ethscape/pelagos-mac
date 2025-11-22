"""is3DModel hook implementation."""

import argparse
import logging
import sys
import zipfile
from pathlib import Path
from typing import Dict, Any, Iterable, Set, List

try:
    import rarfile  # type: ignore
except ImportError:  # pragma: no cover
    rarfile = None

DEFAULT_EXTENSIONS: Set[str] = {
    '.obj',
    '.fbx',
    '.stl',
    '.3ds',
    '.dae',
    '.ply',
    '.blend',
    '.glb',
    '.gltf',
    '.usdz',
    '.usd',
}

logger = logging.getLogger("pelagos.hooks.is3DModel")


def register(registry):
    registry.register('is3DModel', hook)


def hook(file_path: Path, context: Dict[str, Any] | None = None) -> bool:
    if not file_path.exists():
        logger.debug("Hook is3DModel: file does not exist")
        return False

    extensions = _build_extension_set(context)
    suffix = file_path.suffix.lower()

    if suffix in {'.zip', '.cbz'}:
        return _check_zip(file_path, extensions)
    if suffix in {'.rar', '.cbr'}:
        return _check_rar(file_path, extensions)

    logger.debug("Hook is3DModel: unsupported archive type %s", suffix)
    return False


def _build_extension_set(context: Dict[str, Any] | None) -> Set[str]:
    if not context:
        return set(DEFAULT_EXTENSIONS)

    custom = context.get('extensions')
    if not custom:
        return set(DEFAULT_EXTENSIONS)

    if isinstance(custom, Iterable) and not isinstance(custom, (str, bytes)):
        return {str(ext).lower() if str(ext).startswith('.') else f".{str(ext).lower()}" for ext in custom}

    logger.warning("Hook is3DModel: context.extensions should be an iterable of extensions")
    return set(DEFAULT_EXTENSIONS)


def _check_zip(file_path: Path, extensions: Set[str]) -> bool:
    if not zipfile.is_zipfile(file_path):
        logger.debug("Hook is3DModel: invalid zip file")
        return False

    with zipfile.ZipFile(file_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if Path(info.filename).suffix.lower() in extensions:
                return True

    return False


def _check_rar(file_path: Path, extensions: Set[str]) -> bool:
    if rarfile is None:
        logger.debug("Hook is3DModel: rarfile module not available")
        return False

    try:
        with rarfile.RarFile(file_path) as archive:  # type: ignore[attr-defined]
            for info in archive.infolist():
                if info.isdir():
                    continue
                if Path(info.filename).suffix.lower() in extensions:
                    return True
    except rarfile.Error as exc:  # type: ignore[attr-defined]
        logger.debug("Hook is3DModel: invalid rar archive %s", exc)
        return False

    return False


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the is3DModel hook against an archive")
    parser.add_argument("path", type=Path, help="Path to the archive file")
    parser.add_argument(
        "--extension",
        dest="extensions",
        action="append",
        default=[],
        help="Additional file extension to treat as 3D content (can be repeated)",
    )
    parser.add_argument("--quiet", action="store_true", help="Only report PASS/FAIL (suppress debug logs)")

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.quiet else logging.DEBUG)

    context = {}
    if args.extensions:
        context["extensions"] = args.extensions

    result = hook(args.path, context or None)
    if result:
        print(f"PASS: {args.path} contains 3D model assets")
        return 0
    print(f"FAIL: {args.path} does not contain known 3D assets")
    return 1


if __name__ == "__main__":
    sys.exit(main())
