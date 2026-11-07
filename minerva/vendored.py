"""Put the vendored FrontEndSLM on sys.path. Import this before `frontendslm`, `design` or `audit`."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "vendor" / "frontendslm"

for path in (FRONTEND / "src", FRONTEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
