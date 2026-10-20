"""Executable core for the Complete Codebase Review pipeline."""

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def load_pipeline():
    """Return the packaged pipeline manifest as a dict."""
    with open(_ROOT / "pipeline.json", encoding="utf-8") as f:
        return json.load(f)


__version__ = load_pipeline()["version"]
