"""`garage propose URL --topic ID --why "..."`: suggest a new resource. Writes proposals/<date>-<slug>.yaml in the
repo (or --out DIR); never commits or pushes (a human or the coordinator opens the PR; CI validates it; merged
proposals enter as quarantine). The topic must exist. --dry-run prints the file and the path it would write, and
writes nothing. No network: metadata (licence, stars, pushed) is filled by the weekly verify run or the reviewer."""
import datetime
import getpass
import os
import re
from pathlib import Path

from . import catalog, paths

KINDS = ("repo", "skill", "mcp", "plugin", "list", "docs", "guide", "checklist", "template", "snippet", "codepen",
         "tool", "dataset", "course")
USES = ("vendor", "install", "reference", "skill", "mcp", "template", "plugin")


def slug_of(url):
    gh = catalog.github_repo(url)
    if gh:
        base = gh[0].replace("/", "-") + ("-" + gh[1].split("/")[-1] if gh[1] else "")
    else:
        from urllib.parse import urlsplit
        s = urlsplit(url)
        base = s.netloc + s.path
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60] or "item"


def render(p):
    import yaml
    return ("# A proposal for the Code Garage catalog (garage propose). Review, then move into catalog/<slice>.yaml.\n"
            + yaml.safe_dump(p, sort_keys=False, allow_unicode=True, width=120))


def propose(url, topic, why, name=None, kind=None, use=None, license=None, dry_run=False, out=None):
    errors, warnings = [], []
    url = str(url).strip()
    if not re.match(r"^https?://\S+$", url):
        errors.append(f"not a URL: {url!r}")
    if not why or len(why.strip()) < 10:
        errors.append("--why needs a sentence (at least 10 characters): what an agent uses it for")
    if kind and kind not in KINDS:
        errors.append(f"--kind must be one of {', '.join(KINDS)}")
    if use and use not in USES:
        errors.append(f"--use must be one of {', '.join(USES)}")
    cat = catalog.load()
    rid = catalog.normalize_url(url) if not errors else ""
    if rid in cat["resources"]:
        errors.append(f"already in the catalog: {rid} (topics {', '.join(cat['resources'][rid]['topics'])})")
    if not catalog.topic(cat, topic):
        import difflib
        near = difflib.get_close_matches(str(topic), [t["id"] for t in cat["topics"]], n=3, cutoff=0.5)
        errors.append(f"unknown topic {topic!r}: use an existing topic id"
                      + (f" (closest: {', '.join(near)})" if near else "") + "; `garage search WORDS` lists topics")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    gh = catalog.github_repo(url)
    res = {"name": name or (gh[0] if gh else url.split("//", 1)[-1][:80]), "url": url,
           "kind": kind or ("repo" if gh else "docs"), "license": license or "none", "tier": 3,
           "use": use or "reference"}
    today = datetime.date.today().isoformat()
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = os.environ.get("USER", "unknown")
    p = {"proposed": today, "by": user, "topic": topic, "why": why.strip(), "resource": res,
         "status": "proposed", "trust": "quarantine" if catalog.is_runnable(res) else "n/a"}
    if license is None:
        warnings.append("licence unknown until verified (written as 'none')")
    text = render(p)
    folder = Path(out) if out else paths.repo() / "proposals"
    path = folder / f"{today}-{slug_of(url)}.yaml"
    result = {"ok": True, "path": str(path), "proposal": p, "warnings": warnings, "dry_run": bool(dry_run)}
    if dry_run:
        result["text"] = text
        return result
    if path.exists():
        return {"ok": False, "errors": [f"{path} exists already"], "warnings": warnings}
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "errors": [f"can't write {path}: {e} (use --out DIR)"], "warnings": warnings}
    return result
