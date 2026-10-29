"""`garage pin`: pin every GitHub resource of the catalog to a commit (lock/pins.yaml).

  garage pin                    pin new resources to their repo's default-branch HEAD (a repo already pinned for another
                                resource reuses that sha: one snapshot per repo), drop pins of removed resources,
                                recompute path/policy from the catalog. Existing pins never move.
  garage pin --outdated         list upstream movement (default-branch HEAD != pin); changes nothing
  garage pin --bump X [X ...]   move the pins of these rids or owner/name repos to HEAD (all rids of a repo together)
  garage pin --bump-all         the same for every pin (the monthly pin-bump PR)
  garage pin --set RID SHA      pin one resource to a given commit; refused unless the sha is reachable from upstream's
                                default branch (compare status behind|identical: the fork gotcha, design section 4)
  garage pin --check-forks      the same reachability check for every runnable pin that is not upstream's HEAD

Whenever a pin's sha changes, its trust record drops to quarantine first (garage.trust.reset; write()).

GitHub metadata comes from GraphQL in batches of 50 through `gh` (pins.graphql_repos); ~3,200 repos = ~65 calls.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys

from . import catalog as catalog_mod
from . import pins as pins_mod

OK_COMPARE = {"behind", "identical"}


def log(msg):
    print(msg, file=sys.stderr)


def today():
    return dt.date.today().isoformat()


def github_resources(cat):
    """{rid: (repo, path, res)} for every GitHub repository resource in the catalog."""
    out = {}
    for rid, res in cat["resources"].items():
        r = pins_mod.repo_of(res.get("url", ""))
        if r:
            out[rid] = (r[0], pins_mod.path_of(res), res)
    return out


def make_pin(res, repo, path, sha, node_or_prev, pinned):
    if isinstance(node_or_prev, dict) and "license_at_pin" in node_or_prev:   # an existing pin of the same repo
        lic, size, name = node_or_prev["license_at_pin"], node_or_prev["size_kb"], node_or_prev["repo"]
    else:
        lic, size = pins_mod.spdx_of(node_or_prev), int((node_or_prev or {}).get("diskUsage") or 0)
        name = (node_or_prev or {}).get("nameWithOwner") or repo
    return {"repo": name, "sha": sha, "path": path, "pinned": pinned, "license_at_pin": lic, "size_kb": size,
            "policy": pins_mod.policy_for(res, lic, size, path)}


def write(current, new, reason, dry_run=False):
    """The one way pins are written: every rid whose sha moves first drops its trust record to quarantine
    (garage.trust.reset: a review counts only for the commit it read), then lock/pins.yaml is written. -> [reset rids]"""
    moved = sorted(rid for rid, p in new.items() if rid in current and current[rid]["sha"] != p["sha"])
    if dry_run:
        return moved
    if moved:
        from . import trust as trust_mod
        for rid in moved:
            trust_mod.reset(rid, f"{reason}: pin {current[rid]['sha'][:12]} -> {new[rid]['sha'][:12]}")
    pins_mod.dump(new)
    return moved


def compare_status(repo, base, sha):
    """GitHub's compare status of sha against base (the default branch): behind|identical|ahead|diverged|missing."""
    p = subprocess.run(["gh", "api", f"repos/{repo}/compare/{base}...{sha}", "--jq", ".status"],
                       capture_output=True, text=True, timeout=60)
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else "missing"


def reachable(repo, sha, node):
    """(ok, status): the sha must be in upstream's default branch history, not only in some fork."""
    head, branch = pins_mod.head_of(node)
    if not head:
        return False, "no default branch"
    if head == sha:
        return True, "identical"
    st = compare_status(repo, branch, sha)
    return st in OK_COMPARE, st


def cmd_pin(cat, current, args):
    gh = github_resources(cat)
    by_repo = {}
    for rid, p in current.items():
        if rid in gh:
            by_repo.setdefault(p["repo"].lower(), p)
            by_repo.setdefault(gh[rid][0].lower(), p)
    need = sorted({repo for rid, (repo, _, _) in gh.items() if rid not in current and repo.lower() not in by_repo})
    meta = pins_mod.graphql_repos(need, log=log) if need else {}
    new, missing, dropped, changed = {}, [], [], 0
    stamp = today()
    for rid, (repo, path, res) in sorted(gh.items()):
        if rid in current:
            p = dict(current[rid])
            pol = pins_mod.policy_for(res, p["license_at_pin"], p["size_kb"], path)
            if (p.get("path"), p.get("policy")) != (path, pol):
                changed += 1
            p["path"], p["policy"] = path, pol
            new[rid] = p
            continue
        prev = by_repo.get(repo.lower())
        if prev:
            new[rid] = make_pin(res, repo, path, prev["sha"], prev, stamp)
            continue
        node = meta.get(repo)
        sha, _ = pins_mod.head_of(node)
        if not sha:
            missing.append((rid, "not found or no access" if not node else "empty repository"))
            continue
        new[rid] = by_repo[repo.lower()] = make_pin(res, repo, path, sha, node, stamp)
    dropped = sorted(set(current) - set(new))
    added = sorted(set(new) - set(current))
    errs = pins_mod.validate(new)
    if errs:
        log(f"refusing to write: {len(errs)} schema errors, first: {errs[0]}")
        return 1
    write(current, new, "garage pin", args.dry_run)
    summary = {"pins": len(new), "added": len(added), "dropped": len(dropped), "path_or_policy_changed": changed,
               "unresolved": [{"rid": r, "why": w} for r, w in missing],
               "policy": {k: sum(1 for p in new.values() if p["policy"] == k) for k in pins_mod.POLICIES},
               "written": not args.dry_run}
    if args.json:
        print(json.dumps(summary, indent=1))
    else:
        print(f"pins {len(new)}: +{len(added)} -{len(dropped)}, {changed} path/policy updates; "
              + ", ".join(f"{k} {v}" for k, v in summary["policy"].items()))
        for r, w in missing[:20]:
            print(f"  unresolved  {r}  ({w})")
        if len(missing) > 20:
            print(f"  ... {len(missing) - 20} more unresolved")
    return 0


def heads_for(current, repos=None):
    names = sorted({p["repo"] for rid, p in current.items() if repos is None or p["repo"].lower() in repos})
    return pins_mod.graphql_repos(names, log=log)


def cmd_outdated(current, args):
    meta = heads_for(current)
    rows = {}
    for rid, p in current.items():
        node = meta.get(p["repo"])
        head, _ = pins_mod.head_of(node)
        state = "gone" if not node else ("moved" if head and head != p["sha"] else None)
        if state:
            r = rows.setdefault(p["repo"], {"repo": p["repo"], "pinned_sha": p["sha"], "head": head, "state": state,
                                            "pinned": p["pinned"], "rids": 0})
            r["rids"] += 1
    out = sorted(rows.values(), key=lambda r: (r["state"], r["repo"].lower()))
    if args.json:
        print(json.dumps(out, indent=1))
    else:
        for r in out:
            print(f"{r['state']:5}  {r['repo']}  {r['pinned_sha'][:12]} -> {(r['head'] or '-')[:12]}"
                  f"  (pinned {r['pinned']}, {r['rids']} rid)")
        print(f"{len(out)} of {len({p['repo'] for p in current.values()})} pinned repos moved upstream or gone",
              file=sys.stderr)
    return 0


def cmd_bump(cat, current, args):
    gh = github_resources(cat)
    wanted = {x.lower() for x in (args.bump or [])}
    targets = [rid for rid, p in current.items()
               if args.bump_all or rid.lower() in wanted or p["repo"].lower() in wanted]
    repos = {current[r]["repo"].lower() for r in targets}
    targets = [rid for rid, p in current.items() if p["repo"].lower() in repos]   # whole repos move together
    meta = heads_for(current, repos)
    new, moved = dict(current), 0
    for rid in targets:
        p = current[rid]
        node = meta.get(p["repo"])
        head, _ = pins_mod.head_of(node)
        if not head or head == p["sha"] or rid not in gh:
            continue
        repo, path, res = gh[rid]
        new[rid] = make_pin(res, repo, path, head, node, today())
        moved += 1
    reset = write(current, new, "pin bump", args.dry_run)
    print(f"bumped {moved} pins in {len(repos)} repos" + (" (dry run)" if args.dry_run else "")
          + (f"; {len(reset)} trust records {'would drop' if args.dry_run else 'dropped'} to quarantine "
             "(review again)" if reset else ""))
    return 0


def cmd_set(cat, current, args):
    rid, sha = catalog_mod.normalize_url(args.set[0]), args.set[1].lower()
    gh = github_resources(cat)
    if rid not in gh:
        log(f"{rid}: not a GitHub resource of the catalog")
        return 2
    if not pins_mod.SHA_RE.match(sha):
        log("the sha must be the full 40-hex commit id")
        return 2
    repo, path, res = gh[rid]
    node = pins_mod.graphql_repos([repo]).get(repo)
    ok, status = reachable((node or {}).get("nameWithOwner") or repo, sha, node)
    if not ok:
        log(f"refused: {sha[:12]} is not in {repo}'s default branch (compare: {status}); a sha that exists only in "
            "a fork is still served through the upstream URL")
        return 1
    new = dict(current)
    new[rid] = make_pin(res, repo, path, sha, node, today())
    reset = write(current, new, "garage pin --set", args.dry_run)
    print(f"pinned {rid} at {sha[:12]} ({status})" + (" (dry run)" if args.dry_run else "")
          + ("; its trust record drops to quarantine (review again)" if reset else ""))
    return 0


def cmd_check_forks(cat, current, args):
    runnable = {rid for rid, res in cat["resources"].items() if catalog_mod.is_runnable(res)}
    todo = {rid: p for rid, p in current.items() if rid in runnable}
    meta = heads_for(todo)
    bad = []
    for rid, p in sorted(todo.items()):
        ok, status = reachable(p["repo"], p["sha"], meta.get(p["repo"]))
        if not ok:
            bad.append((rid, p["sha"], status))
    for rid, sha, status in bad:
        print(f"FAIL  {rid} {sha[:12]}: {status}")
    print(f"{len(todo) - len(bad)} of {len(todo)} runnable pins reachable from upstream's default branch")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garage pin", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--outdated", action="store_true", help="list upstream movement, change nothing")
    g.add_argument("--bump", nargs="+", metavar="RID|OWNER/NAME")
    g.add_argument("--bump-all", action="store_true")
    g.add_argument("--set", nargs=2, metavar=("RID", "SHA"))
    g.add_argument("--check-forks", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="compute and report, don't write lock/pins.yaml")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cat = catalog_mod.load()
    current = pins_mod.load()
    if args.outdated:
        return cmd_outdated(current, args)
    if args.bump or args.bump_all:
        return cmd_bump(cat, current, args)
    if args.set:
        return cmd_set(cat, current, args)
    if args.check_forks:
        return cmd_check_forks(cat, current, args)
    return cmd_pin(cat, current, args)


if __name__ == "__main__":
    sys.exit(main())
