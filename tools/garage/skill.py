"""`garage skill add ID` / `garage skill list`: agent skills in a project's .claude/skills/<name>/.

add: the same trust gate as `garage add` (garage.trust.allowed; fail closed), then garage.mirror.fetch(rid) into a
temporary folder beside the target, find the SKILL.md (the folder itself, or the one sub-folder `--name` picks when the
item holds several skills), move that folder to .claude/skills/<name>, keep the item's LICENSE/NOTICE files and write
.garage.json (rid, sha, trust at install, date). Claude Code loads it at the next session (or /reload-skills).
list: every installed skill with its .garage.json and today's trust tier (a pin bump can drop it to quarantine).
"""
import datetime
import json
import re
import shutil
from pathlib import Path

from . import add as add_mod, catalog, search

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def skills_dir(project="."):
    return Path(project) / ".claude" / "skills"


def front_name(skill_md):
    """The `name:` of a SKILL.md frontmatter (read as text), or None."""
    try:
        text = Path(skill_md).read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return None
    m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return None
    n = re.search(r"^name:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", m.group(1), re.M)
    return n.group(1).strip() if n else None


def find_skills(root):
    """Folders holding a SKILL.md under root (not following links), shallowest first."""
    root = Path(root)
    found = []
    for p in sorted(root.rglob("SKILL.md")):
        if p.is_file() and not p.is_symlink() and ".git" not in p.parts:
            found.append(p.parent)
    return sorted(found, key=lambda p: (len(p.relative_to(root).parts), str(p)))


def _is_skill(r):
    return r.get("use") == "skill" or r.get("kind") == "skill"


def add(ref, project=".", name=None, force=False, dry_run=False):
    t, res = add_mod.pick(ref, want=_is_skill)
    if res is None:
        return {"ok": False, "action": "unknown", "ref": ref, "reason": f"nothing in the garage matches {ref!r}"}
    rid = res["rid"]
    out = {"rid": rid, "name": res.get("name"), "url": res.get("url"), "license": res.get("license")}
    if not _is_skill(res) and res.get("use") != "plugin":
        return dict(out, ok=False, action="refused", reason=f"{rid} is a {res.get('use')}/{res.get('kind')}, not a skill"
                    " (use garage add)")
    ok, reason = add_mod.check_trust(rid)
    out["trust"] = search.trust_of(res)
    if not ok:
        return dict(out, ok=False, action="refused", reason=reason)
    sdir = skills_dir(project)
    if dry_run:
        return dict(out, ok=True, action="would-install", dest=str(sdir / (name or add_mod.slug(res))))
    sdir.mkdir(parents=True, exist_ok=True)
    tmp = sdir / f".garage-tmp-{add_mod.slug(res)}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        fetched = Path(add_mod.fetch(rid, tmp) or tmp)
        skills = find_skills(fetched)
        if not skills:
            return dict(out, ok=False, action="refused", reason="no SKILL.md in this item")
        if name:
            pick = [s for s in skills if s.name == name or front_name(s / "SKILL.md") == name]
            if not pick:
                return dict(out, ok=False, action="refused", reason=f"no skill named {name!r} in this item",
                            skills=[s.name for s in skills[:20]])
            src = pick[0]
        elif len(skills) == 1 or skills[0] == fetched:
            src = skills[0]
        else:
            return dict(out, ok=False, action="choose", reason="this item holds several skills: pick one with --name",
                        skills=[s.name for s in skills[:30]])
        sname = front_name(src / "SKILL.md") or src.name
        if not NAME_RE.match(sname):
            sname = re.sub(r"[^a-z0-9-]+", "-", sname.lower()).strip("-")[:64] or add_mod.slug(res)
        dest = sdir / sname
        if dest.exists():
            if not force:
                return dict(out, ok=False, action="refused", dest=str(dest),
                            reason=f"{dest} exists (use --force to replace it)")
            shutil.rmtree(dest)
        meta = {}
        mf = fetched / ".garage.json"
        if mf.is_file():
            try:
                meta = json.loads(mf.read_text())
            except ValueError:
                meta = {}
        if src != fetched:
            for f in fetched.iterdir():   # the item's licence files travel with the skill
                if f.is_file() and re.match(r"(LICEN[CS]E|COPYING|NOTICE)", f.name, re.I) and not (src / f.name).exists():
                    shutil.copy2(f, src / f.name)
        shutil.move(str(src), str(dest))
        meta.update({"rid": rid, "skill": sname, "trust_at_install": out["trust"],
                     "installed": datetime.date.today().isoformat(), "garage_ref": ref})
        if src != fetched:
            meta["source_path"] = str(src.relative_to(fetched))
        (dest / ".garage.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        return dict(out, ok=True, action="installed", skill=sname, dest=str(dest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def list_skills(project="."):
    out = []
    sdir = skills_dir(project)
    if not sdir.is_dir():
        return out
    cat = None
    for d in sorted(p for p in sdir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        item = {"skill": d.name, "path": str(d), "garage": False}
        mf = d / ".garage.json"
        if mf.is_file():
            try:
                meta = json.loads(mf.read_text())
            except ValueError:
                meta = {}
            item.update(garage=True, rid=meta.get("rid"), sha=meta.get("sha"), installed=meta.get("installed"),
                        trust_at_install=meta.get("trust_at_install"))
            cat = cat or catalog.load()
            res = cat["resources"].get(meta.get("rid"))
            item["trust"] = search.trust_of(res) if res else "unknown (not in the catalog any more)"
        out.append(item)
    return out
