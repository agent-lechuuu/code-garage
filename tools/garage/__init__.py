"""Code Garage: a curated, pinned library of existing code, skills, MCP servers and templates for coding agents.

Modules: paths catalog search index validate add skill new propose doctor cli (catalog + CLI) · pins pin mirror verify
(mirror) · trust policy scan review promote (safety) · mcp_server (MCP). Other tracks' modules are optional at import
time: use optional("mirror") etc., which returns the module or None.
"""
import importlib

__version__ = "0.1.0"

_missing = set()


def optional(name):
    """garage.<name> if it exists and imports, else None (the caller falls back or says what's missing)."""
    if name in _missing:
        return None
    try:
        return importlib.import_module(f"garage.{name}")
    except ImportError as e:
        if getattr(e, "name", "") not in (f"garage.{name}", name):
            raise   # the module exists but one of *its* imports is broken: show that, don't hide it
        _missing.add(name)
        return None
