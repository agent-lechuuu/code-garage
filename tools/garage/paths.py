"""Where the garage lives. Everything comes from the environment, with defaults that work on the server and anywhere.

  GARAGE_HOME   the data folder (mirror, quarantine, index, state). Default: /data/apps/garage when that folder exists
                (the home server), else ~/.garage (the Mac, anyone).
  GARAGE_REPO   the code-garage checkout (catalog/, lock/, trust/, dist/). Default: $GARAGE_HOME/repo when it holds a
                catalog, else the checkout this package runs from (tools/garage/../..), else $GARAGE_HOME/repo.
"""
import os
from pathlib import Path

SERVER_HOME = Path("/data/apps/garage")
SRC = Path(__file__).resolve().parent.parent.parent   # tools/garage/paths.py -> the checkout (when run from one)


def _has_catalog(p):
    return (p / "catalog").is_dir() or (p / "dist" / "catalog.json").is_file()


def home():
    env = os.environ.get("GARAGE_HOME")
    if env:
        return Path(env).expanduser()
    if SERVER_HOME.is_dir():
        return SERVER_HOME
    return Path.home() / ".garage"


def repo():
    env = os.environ.get("GARAGE_REPO")
    if env:
        return Path(env).expanduser()
    deployed = home() / "repo"
    if _has_catalog(deployed):
        return deployed
    if _has_catalog(SRC):
        return SRC
    return deployed


def mirror():
    return home() / "mirror"


def quarantine():
    return home() / "quarantine"


def index_db():
    return home() / "index" / "garage.db"


def state():
    return home() / "state"


def health():
    from .catalog import PACKAGED
    if repo().is_dir():
        out = [("PASS", f"repo {repo()}")]
    elif PACKAGED.is_file():   # pip/uvx install off-server: the catalog, pins and trust come bundled
        out = [("PASS", f"repo: none at {repo()}; using the catalog bundled in the package")]
    else:
        out = [("FAIL", f"repo {repo()}")]
    out.append(("PASS" if home().is_dir() else "WAIT", f"GARAGE_HOME {home()}"))
    for name, p in (("mirror", mirror()), ("quarantine", quarantine()), ("state", state())):
        out.append(("PASS" if p.is_dir() else "WAIT", f"{name} {p}"))
    return out
