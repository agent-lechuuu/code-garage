"""garage: the Code Garage command line. `garage <command> --help` for each; `--json` prints the API dicts.

  search WORDS      find topics and their best resource (filters: --kind --use --slice --trust --license)
  show ID|URL       a topic or resource with its recipe (install line, local path, licence, trust, practices)
  grep ID PATTERN   ripgrep inside one mirrored snapshot
  add ID            copy a pinned item into the project (trust-gated); packages print their install line
  skill add|list    agent skills in .claude/skills/
  new NAME          start a project (optionally from a template) with a CLAUDE.md that says: search the garage first
  propose URL       write proposals/<date>-<slug>.yaml for review (never pushes)
  index             rebuild the search index        build      regenerate INDEX.md + dist/
  validate          check the catalog (CI)          doctor     health of every module
  pin pins mirror verify (mirror track) · scan review promote (safety track): garage.<cmd>.main(argv)
"""
import argparse
import json
import sys

from . import __version__

DELEGATED = {"pin": "pin", "pins": "pin", "mirror": "mirror", "verify": "verify", "scan": "scan",
             "review": "review", "promote": "promote"}


def emit(obj, as_json, human):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=None if isinstance(obj, list) and len(obj) > 20 else 1))
    else:
        human(obj)


def _kv(d, keys):
    return " · ".join(str(d[k]) for k in keys if d.get(k) not in (None, ""))


# ---- commands

def cmd_search(a):
    from . import search
    r = search.search(" ".join(a.words), kind=a.kind, use=a.use, slice=a.slice, trust=a.trust, license=a.license,
                      limit=a.limit)
    from . import index
    if index.state.get("note"):
        print(f"note: {index.state['note']}", file=sys.stderr)

    def human(rs):
        if not rs:
            print("(nothing found; try other words or fewer filters)")
        for k, h in enumerate(rs, 1):
            b = h["best"]
            print(f"{k}. {h['id']}  {h['title']}")
            print(f"   {h['why']}")
            print(f"   best: {b['name']} <{b['url']}> " + _kv(b, ("kind", "use", "license")) +
                  (f" · trust {b['trust']}" if b.get("trust") != "n/a" else ""))
            if b.get("install"):
                print(f"   use:  {b['install']}")
            if b.get("local_path"):
                print(f"   local: {b['local_path']}")
    emit(r, a.json, human)
    return 0


def cmd_show(a):
    from . import search
    r = search.show(a.ref)

    def human(d):
        if not d:
            print(f"(nothing in the garage matches {a.ref!r}; try garage search)")
            return
        if "resources" in d:
            print(f"{d['id']}  {d['title']}  ({d['slice']}/{d['area']})")
            print(f"  {d['why']}")
            for p in d.get("practices") or []:
                print(f"  rule: {p}")
            for r in d["resources"]:
                print(f"- {r.get('name')} <{r.get('url')}>")
                print("    " + _kv(r, ("kind", "use", "license")) + f" · tier {r.get('tier')}" +
                      (f" · trust {r['trust']}" if r.get("trust") != "n/a" else ""))
                for k in ("install", "local_path", "path", "note"):
                    if r.get(k):
                        print(f"    {k}: {r[k]}")
                if r.get("pin"):
                    print(f"    pin: {r['pin'].get('sha', '')[:12]} ({r['pin'].get('pinned', '')})")
            if d.get("see_also"):
                print("  see also: " + ", ".join(d["see_also"]))
        else:
            for k, v in d.items():
                print(f"{k}: {v}")
    emit(r, a.json, human)
    return 0 if r else 1


def cmd_grep(a):
    from . import search
    r = search.grep(a.ref, a.pattern, ignore_case=a.ignore_case, limit=a.limit)

    def human(d):
        if not d.get("ok"):
            print(d.get("reason"), file=sys.stderr)
            return
        for m in d["matches"]:
            print(f"{m['file']}:{m['line']}:{m['text']}")
        if d.get("truncated"):
            print(f"(stopped at {len(d['matches'])} matches; --limit N for more)", file=sys.stderr)
    emit(r, a.json, human)
    return 0 if r.get("ok") else 1


def _result(r, a):
    def human(d):
        if d.get("ok"):
            act = d.get("action")
            if act == "install" and d["install"].startswith("install as"):
                print(f"{d['name']}: a package, {d['install']}")
            elif act == "install":
                print(f"{d['name']}: a package, install it with:\n  {d['install']}")
            elif act == "reference":
                print(f"{d['name']}: read it at {d.get('local_path') or d['url']}" +
                      (f"\n  {d['install']}" if d.get("install") else ""))
            else:
                print(f"{act}: {d.get('name') or d.get('name')} -> {d.get('dest') or d.get('path')}")
            if d.get("licence_warning"):
                print("note: " + d["licence_warning"])
            for w in d.get("warnings") or []:
                print("warning: " + w)
        else:
            for e in d.get("errors") or [d.get("reason")]:
                print(f"refused: {e}", file=sys.stderr)
            if d.get("skills"):
                print("skills: " + ", ".join(d["skills"]), file=sys.stderr)
    emit(r, a.json, human)
    return 0 if r.get("ok") else 1


def cmd_add(a):
    from . import add
    return _result(add.add(a.ref, into=a.into, dry_run=a.dry_run), a)


def cmd_skill(a):
    from . import skill
    if a.action == "list":
        r = skill.list_skills(a.project)

        def human(rs):
            if not rs:
                print(f"(no skills in {skill.skills_dir(a.project)})")
            for s in rs:
                extra = f"{s.get('rid')} · trust now {s.get('trust')}" if s.get("garage") else "(not from the garage)"
                print(f"{s['skill']}: {extra}")
        emit(r, a.json, human)
        return 0
    if not a.ref:
        print("garage skill add ID", file=sys.stderr)
        return 2
    return _result(skill.add(a.ref, project=a.project, name=a.name, force=a.force, dry_run=a.dry_run), a)


def cmd_new(a):
    from . import new
    return _result(new.new(a.name, template=a.template, parent=a.parent, dry_run=a.dry_run), a)


def cmd_propose(a):
    from . import propose
    r = propose.propose(a.url, a.topic, a.why, name=a.name, kind=a.kind, use=a.use, license=a.license,
                        dry_run=a.dry_run, out=a.out)
    if r.get("ok") and a.dry_run and not a.json:
        print(r["text"], end="")
        print(f"(dry run: would write {r['path']})")
        return 0
    return _result(r, a)


def cmd_index(a):
    from . import index
    r = index.build(db=a.db)
    emit(r, a.json, lambda d: print(f"index {d['db']}: {d['rows']} rows ({d['topics']} topics, {d['resources']} "
                                    f"resources, {d['mirror_chunks']} mirror chunks), {d['kb']} kB, {d['seconds']} s"))
    return 0


def cmd_build(a):
    from . import index
    r = index.write_dist(check=a.check)
    out = {"check": a.check, "stale" if a.check else "written": r}

    def human(d):
        if a.check:
            print("generated files are fresh" if not r else "stale (run garage build): " + ", ".join(r))
        else:
            print("written: " + (", ".join(r) if r else "nothing (already fresh)"))
    emit(out, a.json, human)
    return 1 if a.check and r else 0


def cmd_validate(a):
    from . import validate
    if a.guard is not None:
        bad = validate.guard(a.guard)
        emit({"ok": not bad, "errors": bad}, a.json, lambda d: [print(x) for x in d["errors"]])
        return 1 if bad else 0
    errors, warnings = validate.validate()
    out = {"ok": not errors, "errors": errors, "warnings": warnings}

    def human(d):
        for e in errors:
            print(f"ERROR {e}")
        for w in warnings:
            print(f"warn  {w}")
        print(f"{'ok' if not errors else 'FAILED'}: {len(errors)} errors, {len(warnings)} warnings")
    emit(out, a.json, human)
    return 1 if errors else 0


def cmd_doctor(a):
    from . import doctor
    r = doctor.doctor()
    emit(r, a.json, lambda rs: [print(f"{x['status']} {x['module']}: {x['text']}") for x in rs])
    return 1 if any(x["status"] == "FAIL" for x in r) else 0


def delegate(cmd, argv):
    from . import optional
    mod = optional(DELEGATED[cmd])
    track = "mirror (T2)" if cmd in ("pin", "pins", "mirror", "verify") else "safety (T4)"
    if mod is None or not hasattr(mod, "main"):
        print(f"garage {cmd}: the {track} module garage.{DELEGATED[cmd]} is not installed in this checkout",
              file=sys.stderr)
        return 3
    if cmd == "pins":   # `garage pins --outdated` (the spec's spelling) = `garage pin --outdated`
        argv = argv or ["--help"]   # never "pin everything" by accident
    return mod.main(argv) or 0


def parser():
    ap = argparse.ArgumentParser(prog="garage", description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n", 2)[2])
    ap.add_argument("--version", action="version", version=f"garage {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def cmd(name, fn, help_):
        p = sub.add_parser(name, help=help_, description=help_)
        p.add_argument("--json", action="store_true", help="print the result as JSON")
        p.set_defaults(fn=fn)
        return p

    p = cmd("search", cmd_search, "find topics and their best resource")
    p.add_argument("words", nargs="+")
    p.add_argument("--kind", help="repo, skill, mcp, plugin, template, docs, ... (comma list)")
    p.add_argument("--use", help="vendor, install, reference, skill, mcp, template, plugin (comma list)")
    p.add_argument("--slice", help="ai, backend, engineering, frontend, security, systems, web3, garage")
    p.add_argument("--trust", help="quarantine, reviewed, trusted, n/a")
    p.add_argument("--license", help="an SPDX id (prefix) or 'permissive'")
    p.add_argument("-n", "--limit", type=int, default=5)
    p = cmd("show", cmd_show, "a topic or resource with its recipe")
    p.add_argument("ref", help="topic id, URL, owner/repo or resource name")
    p = cmd("grep", cmd_grep, "ripgrep inside one mirrored snapshot")
    p.add_argument("ref")
    p.add_argument("pattern")
    p.add_argument("-i", "--ignore-case", action="store_true")
    p.add_argument("--limit", type=int, default=100)
    p = cmd("add", cmd_add, "copy a pinned item into the project (trust-gated)")
    p.add_argument("ref")
    p.add_argument("--into", default="vendor", help="parent folder (default vendor/)")
    p.add_argument("--dry-run", action="store_true")
    p = cmd("skill", cmd_skill, "install or list agent skills in .claude/skills/")
    p.add_argument("action", choices=("add", "list"))
    p.add_argument("ref", nargs="?")
    p.add_argument("--project", default=".", help="project folder (default .)")
    p.add_argument("--name", help="which skill, when the item holds several")
    p.add_argument("--force", action="store_true", help="replace an installed skill of the same name")
    p.add_argument("--dry-run", action="store_true")
    p = cmd("new", cmd_new, "start a project with a garage CLAUDE.md")
    p.add_argument("name")
    p.add_argument("--template", help="garage id of a template to start from")
    p.add_argument("--parent", default=".")
    p.add_argument("--dry-run", action="store_true")
    p = cmd("propose", cmd_propose, "write a proposal for a new resource (never pushes)")
    p.add_argument("url")
    p.add_argument("--topic", required=True)
    p.add_argument("--why", required=True)
    p.add_argument("--name")
    p.add_argument("--kind")
    p.add_argument("--use")
    p.add_argument("--license")
    p.add_argument("--out", help="folder for the proposal (default $GARAGE_REPO/proposals)")
    p.add_argument("--dry-run", action="store_true")
    p = cmd("index", cmd_index, "rebuild the search index")
    p.add_argument("--db", help="index file (default $GARAGE_HOME/index/garage.db)")
    p = cmd("build", cmd_build, "regenerate INDEX.md and dist/ (catalog.json, index/<slice>.md)")
    p.add_argument("--check", action="store_true", help="write nothing; exit 1 if the files are stale (CI)")
    p = cmd("validate", cmd_validate, "check the catalog (schema, ids, see_also, policy)")
    p.add_argument("--guard", nargs="*", metavar="FILE", help="repo guard for pre-commit: refuse media/archives/db/big")
    cmd("doctor", cmd_doctor, "health of every module")
    for name in DELEGATED:
        sub.add_parser(name, help=f"(garage.{DELEGATED[name]}) see garage {name} --help", add_help=False)
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in DELEGATED:
        return delegate(argv[0], argv[1:])
    a = parser().parse_args(argv)
    try:
        return a.fn(a)
    except BrokenPipeError:
        return 0
    except FileNotFoundError as e:
        print(f"garage: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
