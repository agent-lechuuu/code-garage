"""`garage add ID [--into DIR]`: copy a pinned item into a project.

Runnable items (skill, mcp, plugin, template, vendor, snippet) are copied by garage.mirror.fetch(rid, dest) at their
pinned sha (LICENSE/NOTICE kept, .garage.json written), but only after garage.trust.allowed(rid, unattended) says so:
GARAGE_UNATTENDED=1 -> trusted only; interactive -> reviewed or trusted; quarantine -> never (read it with show/grep).
Without the trust module nothing runnable is added (fail closed). Packages (`use: install`) print their install line;
references print where to read them. Nothing from the mirror is ever executed.

  pick(ref) -> (topic or None, resource or None)
  add(ref, into="vendor", dest=None, dry_run=False) -> {ok, action, rid, name, ...}
"""
import os
import re
from pathlib import Path

from . import catalog, optional, search


def unattended():
    return os.environ.get("GARAGE_UNATTENDED") == "1"


def pick(ref, want=None):
    """The resource an id means: a URL/rid/name as given; for a topic, its first runnable resource (or `want`)."""
    t, rs = search.resolve(ref)
    if not rs:
        return t, None
    if t:
        ok = [r for r in rs if (want(r) if want else catalog.is_runnable(r))]
        return t, (ok or rs)[0]
    return None, rs[0]


def slug(res):
    gh = catalog.github_repo(res.get("url", ""))
    base = (gh[1].rstrip("/").split("/")[-1] if gh and gh[1] else gh[0].split("/")[1]) if gh else res.get("name", "")
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(base)).strip("-.").lower()
    return s or "item"


def check_trust(rid):
    """-> (ok, reason) from garage.trust; closed when the module is missing or fails."""
    t = optional("trust")
    if t is None:
        return False, "garage.trust is not installed, so trust can't be checked: nothing runnable is added"
    try:
        return t.allowed(rid, unattended())
    except Exception as e:   # noqa: BLE001 - fail closed
        return False, f"trust check failed: {e}"


def fetch(rid, dest):
    m = optional("mirror")
    if m is None:
        raise RuntimeError("garage.mirror is not installed: can't fetch snapshots yet")
    return m.fetch(rid, str(dest))


def add(ref, into="vendor", dest=None, dry_run=False):
    t, res = pick(ref)
    if res is None:
        return {"ok": False, "action": "unknown", "ref": ref,
                "reason": f"nothing in the garage matches {ref!r} (try: garage search WORDS)"}
    rid = res["rid"]
    out = {"rid": rid, "name": res.get("name"), "url": res.get("url"), "license": res.get("license"),
           "use": res.get("use"), "kind": res.get("kind")}
    if t:
        out["topic"] = t["id"]
    if not catalog.is_runnable(res):
        line = search.install_line(res)
        if res.get("use") == "install" and line:
            return dict(out, ok=True, action="install", install=line)
        return dict(out, ok=True, action="reference", install=line, local_path=search.index.local_path(rid),
                    reason="not something to copy: read it (garage show / garage grep) or install it as a package")
    ok, reason = check_trust(rid)
    out["trust"] = search.trust_of(res)
    if not ok:
        return dict(out, ok=False, action="refused", reason=reason)
    target = Path(dest) if dest else Path(into) / slug(res)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        return dict(out, ok=False, action="refused", dest=str(target), reason=f"{target} exists and is not empty")
    lic = str(res.get("license") or "none")
    if not catalog.is_permissive(lic):
        out["licence_warning"] = (f"licence {lic}: keep its LICENSE/NOTICE files and check the terms before "
                                  "shipping (copyleft or unclear licences have duties)")
    if dry_run:
        return dict(out, ok=True, action="would-copy", dest=str(target))
    path = fetch(rid, target)
    return dict(out, ok=True, action="copied", dest=str(path or target))
