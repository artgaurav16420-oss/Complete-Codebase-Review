"""Executable core for the Complete Codebase Review pipeline."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def load_pipeline():
    """Return the packaged pipeline manifest as a dict.

    Returns an empty dict when the manifest is unavailable or invalid so that
    importing ``ccr`` does not fail outside an installed skill tree.
    """
    path = _ROOT / "pipeline.json"
    if not path.exists():
        return {}
    from .manifest import load as load_manifest
    try:
        return load_manifest(path)
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return {}


_manifest = load_pipeline()
__version__ = _manifest.get("version", "0.0.0")
