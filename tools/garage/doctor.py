"""`garage doctor`: every module's health() -> [(PASS|FAIL|WAIT, text)], missing modules as WAIT."""
from . import optional

MODULES = ("paths", "catalog", "validate", "index", "search", "pins", "pin", "mirror", "verify", "trust", "policy",
           "scan", "review", "promote", "mcp_server")


def doctor():
    out = []
    for name in MODULES:
        try:
            m = optional(name)
        except Exception as e:   # noqa: BLE001 - a module that fails to import is a finding, not a crash
            out.append({"module": name, "status": "FAIL", "text": f"import failed: {e}"})
            continue
        if m is None:
            out.append({"module": name, "status": "WAIT", "text": "not installed yet"})
            continue
        h = getattr(m, "health", None)
        if h is None:
            out.append({"module": name, "status": "PASS", "text": "loaded (no health check)"})
            continue
        try:
            for status, text in h() or []:
                out.append({"module": name, "status": status, "text": text})
        except Exception as e:   # noqa: BLE001
            out.append({"module": name, "status": "FAIL", "text": f"health() raised {type(e).__name__}: {e}"})
    return out
