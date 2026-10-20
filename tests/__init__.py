# Complete Codebase Review — test suite.
# Test discovery is handled by unittest.TestCase; this file
# enables `python -m unittest discover -s tests` to work.

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
