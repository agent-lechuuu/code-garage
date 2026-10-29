"""`python3 -I -m garage ...` (installed) or `python3 -I tools/garage ...` (from a checkout, nothing installed)."""
import sys

if not __package__:   # run as a folder: make `import garage` find tools/garage
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "garage"   # noqa: A001

from garage.cli import main  # noqa: E402

sys.exit(main())
