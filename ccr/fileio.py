"""Version-compatible file helpers.

`Path.write_text(..., newline=...)` was added in Python 3.10, but this
project supports 3.9. Route explicit newline writes through `open()`.
"""


def write_text(path, text, newline="\n"):
    """Write UTF-8 text with explicit newline handling on Python 3.9+."""
    with open(path, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)
