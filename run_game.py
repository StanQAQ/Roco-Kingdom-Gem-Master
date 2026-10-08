"""GUI-first entry point used by the standalone Windows build."""
from __future__ import annotations

import sys

from src.cli import main


if __name__ == "__main__":
    if "--gui" not in sys.argv:
        sys.argv.append("--gui")
    main()
