#!/usr/bin/env python3
"""Compatibility shim.

The CLI now lives at ``sdk/python/bxp_cli.py`` so that it ships inside the
``bxp-sdk`` distribution alongside the modules it imports. This shim keeps
``python cli/bxp_cli.py ...`` working, which is the invocation shown throughout
the README.

New code should use the installed console script instead:

    bxp generate --pm25 47.2 --lat 5.6037 --lon -0.1870

or, without installing:

    python sdk/python/bxp_cli.py generate --pm25 47.2 --lat 5.6037 --lon -0.1870
"""

import sys
from pathlib import Path

SDK = Path(__file__).resolve().parent.parent / "sdk" / "python"

if str(SDK) not in sys.path:
    sys.path.insert(0, str(SDK))

from bxp_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())