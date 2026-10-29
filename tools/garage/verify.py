"""`garage verify`: the weekly freshness sweep (no Claude, design section 7).

  garage verify --dry-run       sweep and write the report to state/reports/ (or --out DIR); change nothing else
  garage verify --pr            the timer's mode: also a branch "verify/<ISO week>" in a git worktree under state/
                                (never the deployed checkout) with the catalog metadata updates + the report, pushed,
                                and a PR "verify <week>" opened with gh. No origin or no gh login: report only.

What it finds: over every GitHub repo of the catalog (GraphQL, 50 a call): gone (not found), moved (GitHub answers
with another owner/name), archived (catalog still says archived: false), licence changed (against the pin's
license_at_pin), upstream moved past the pin (count only; pins never move on their own). Over the other http(s) URLs:
lychee (cache in state/, 6 days) for dead links. Metadata it rewrites in the PR: archived (+ tier 3 and an
"ARCHIVED upstream" note), url for moved repos, pushed, and stars when they moved by more than 10 %.
Gone repos and dead links are only reported: replacing them is a recommendation change, the owner's call.

Report: reports/verify-<YYYY>-W<ww>.md, at most 20 lines. Detail: state/verify-<week>.json.
Tests and dry runs: GARAGE_GH_FIXTURE (pins.graphql_repos) and GARAGE_LYCHEE_FIXTURE ({url: "ok"|"<error text>"}).
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import catalog as catalog_mod
from . import paths
from . import pins as pins_mod

GQL = """
  nameWithOwner isArchived pushedAt stargazerCount
  licenseInfo { spdxId }
  defaultBranchRef { name target { oid } }
"""
MAX_LINES = 20
LYCHEE = os.environ.get("GARAGE_LYCHEE", "lychee")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def iso_week(d=None):
    y, w, _ = (d or dt.date.today()).isocalendar()
    return f"{y}-W{w:02d}"


# ---- sweep ----------------------------------------------------------------------------------------------------------

def sweep(cat, pins, lychee=True):
    gh, other = {}, []
    for rid, res in cat["resources"].items():
        r = pins_mod.repo_of(res.get("url", ""))
        if r:
            gh.setdefault(r[0], []).append((rid, res))
        elif str(res.get("url", "")).startswith(("http://", "https://")):
            other.append(rid)
    meta = pins_mod.graphql_repos(sorted(gh), fields=GQL, log=log)
    f = {"gone": [], "moved": [], "archived": [], "licence": [], "upstream_moved": 0, "metadata": [], "dead": [],
         "repos": len(gh), "urls": len(other), "lychee": "not run"}
    for repo, items in sorted(gh.items(), key=lambda kv: kv[0].lower()):
        node = meta.get(repo)
        rids = [rid for rid, _ in items]
        if not node:
            f["gone"].append({"repo": repo, "rids": rids})
            continue
        now_name = node["nameWithOwner"]
        if now_name.lower() != repo.lower():
            f["moved"].append({"repo": repo, "to": now_name, "rids": rids})
        if node.get("isArchived") and any(not res.get("archived") for _, res in items):
            f["archived"].append({"repo": now_name, "rids": [rid for rid, res in items if not res.get("archived")]})
        spdx = pins_mod.spdx_of(node)
        head, _ = pins_mod.head_of(node)
        pinned = [pins[rid] for rid in rids if rid in pins]
        if pinned and spdx != pinned[0]["license_at_pin"]:
            f["licence"].append({"repo": now_name, "was": pinned[0]["license_at_pin"], "now": spdx})
        if pinned and head and head != pinned[0]["sha"]:
            f["upstream_moved"] += 1
        pushed = (node.get("pushedAt") or "")[:10]
        stars = node.get("stargazerCount")
        for rid, res in items:
            ch = {}
            if node.get("isArchived") and not res.get("archived"):
                ch.update(archived=True, tier=3)
            if now_name.lower() != repo.lower():
                ch["url"] = str(res["url"]).replace(f"github.com/{repo}", f"github.com/{now_name}", 1)
            if pushed and "pushed" in res and str(res["pushed"]) != pushed:
                ch["pushed"] = pushed
            old = res.get("stars")
            if isinstance(stars, int) and isinstance(old, int) and abs(stars - old) > max(10, old // 10):
                ch["stars"] = stars
            if ch:
                f["metadata"].append({"rid": rid, "url": res["url"], "changes": ch})
    if lychee:
        f["dead"], f["lychee"] = check_links([cat["resources"][r]["url"] for r in other])
    return f


def check_links(urls):
    """([{url, error}], status line) via lychee; GARAGE_LYCHEE_FIXTURE replaces it."""
    fx = os.environ.get("GARAGE_LYCHEE_FIXTURE")
    if fx:
        with open(fx, encoding="utf-8") as fh:
            res = json.load(fh)
        return [{"url": u, "error": res[u]} for u in urls if res.get(u, "ok") != "ok"], "fixture"
    if not shutil.which(LYCHEE):
        return [], "lychee not installed"
    work = paths.state() / "lychee"
    work.mkdir(parents=True, exist_ok=True)
    (work / "urls.txt").write_text("\n".join(sorted(set(urls))) + "\n", encoding="utf-8")
    cmd = [LYCHEE, "--no-progress", "--format", "json", "--output", "out.json", "--cache", "--max-cache-age", "6d",
           "--timeout", "20", "--max-retries", "2", "--max-concurrency", "16", "--accept", "200..=299,403,429",
           "urls.txt"]
    p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=1800)
    try:
        out = json.loads((work / "out.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], f"lychee failed (exit {p.returncode}): {p.stderr.strip()[-200:]}"
    dead = []
    for items in (out.get("error_map") or out.get("fail_map") or {}).values():
        for it in items:
            st = it.get("status") or {}
            dead.append({"url": it.get("url"), "error": st.get("text") or str(st)})
    return dead, f"lychee {out.get('total', 0)} checked, {out.get('timeouts', 0)} timeouts (not counted)"


# ---- report ---------------------------------------------------------------------------------------------------------

def report(f, week):
    def few(items, fmt, n=3):
        s = ", ".join(fmt(x) for x in items[:n])
        return s + (f" (+{len(items) - n} more)" if len(items) > n else "")

    lines = [f"# verify {week}", "",
             f"{f['repos']} GitHub repos, {f['urls']} other URLs ({f['lychee']}). "
             f"{f['upstream_moved']} pinned repos moved upstream (pins unchanged; `garage pin --outdated`).", "",
             "| finding | n | examples | action |", "|---|---|---|---|",
             f"| archived | {len(f['archived'])} | {few(f['archived'], lambda x: x['repo'])} | archived: true, tier 3 |",
             f"| moved | {len(f['moved'])} | {few(f['moved'], lambda x: x['repo'] + ' -> ' + x['to'])} | url rewritten |",
             f"| gone | {len(f['gone'])} | {few(f['gone'], lambda x: x['repo'])} | owner: remove or replace |",
             f"| licence changed | {len(f['licence'])} | "
             f"{few(f['licence'], lambda x: x['repo'] + ' ' + x['was'] + '->' + x['now'])} | owner: re-check use |",
             f"| dead links | {len(f['dead'])} | {few(f['dead'], lambda x: x['url'])} | owner: remove or replace |",
             f"| metadata updates | {len(f['metadata'])} | stars/pushed/archived/url | in this PR |", "",
             "Pure metadata may be merged as is; gone, licence and dead-link rows change recommendations.",
             f"Detail: state/verify-{week}.json on the server."]
    return [x.replace("\n", " ")[:400] for x in lines[:MAX_LINES]]


# ---- catalog edits (line-based: comments and layout stay as the humans wrote them) ----------------------------------

def _scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return str(v) if re.match(r"^[A-Za-z0-9:/._%~+-]+$", str(v)) and not re.match(r"^\d", str(v)) else json.dumps(v)


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _key_at(line, key, indent):
    """The value part when line sets `key` at the resource's key indent (plain or as the `- ` item line)."""
    m = re.match(r"^(\s*)(- )?" + re.escape(key) + r":\s*(.*)$", line)
    if m and len(m.group(1)) + (2 if m.group(2) else 0) == indent:
        return m
    return None


def edit_yaml(text, changes_by_url):
    """Apply {url: {key: value}} to resource entries in one slice file's text. Returns (text, applied count)."""
    lines = text.split("\n")
    applied, i = 0, 0
    while i < len(lines):
        m = re.match(r"^(\s*)(- )?url:\s*['\"]?([^'\"\s#]+)['\"]?\s*$", lines[i])
        if not m or m.group(3) not in changes_by_url:
            i += 1
            continue
        ch = changes_by_url[m.group(3)]
        ki = len(m.group(1)) + (2 if m.group(2) else 0)
        start = i
        if not m.group(2):
            j = i - 1
            while j >= 0 and (not lines[j].strip() or _indent(lines[j]) >= ki):
                j -= 1
            if j >= 0 and re.match(r"^\s*- ", lines[j]) and _indent(lines[j]) == ki - 2:
                start = j
        end = i + 1
        while end < len(lines) and (not lines[end].strip() or _indent(lines[end]) >= ki):
            end += 1
        for k, v in ch.items():
            if k == "url":
                lines[i] = lines[i].replace(m.group(3), v)
                continue
            hit = next((j for j in range(start, end) if _key_at(lines[j], k, ki)), None)
            if hit is None:
                lines.insert(i + 1, " " * ki + f"{k}: {_scalar(v)}")
                end += 1
            else:
                km = _key_at(lines[hit], k, ki)
                lines[hit] = lines[hit][:km.start(3)] + _scalar(v)
        if ch.get("archived"):
            for j in range(start, end):
                nm = _key_at(lines[j], "note", ki)
                val = nm.group(3) if nm else ""
                if nm and len(val) > 1 and val[0] == val[-1] and val[0] in "\"'" and "ARCHIVED" not in val:
                    lines[j] = lines[j][:nm.start(3)] + val[0] + f"ARCHIVED upstream ({iso_week()}). " + val[1:]
                    break
        applied += 1
        i = end
    return "\n".join(lines), applied


def apply_edits(repo_dir, f):
    import yaml
    by_url = {x["url"]: x["changes"] for x in f["metadata"]}
    total = 0
    for p in sorted((Path(repo_dir) / "catalog").glob("*.yaml")):
        text = p.read_text(encoding="utf-8")
        before = yaml.safe_load(text) or {}
        new, n = edit_yaml(text, by_url)
        if not n:
            continue
        after = yaml.safe_load(new) or {}
        cnt = lambda d: sum(len(t.get("resources") or []) for t in d.get("topics") or [])   # noqa: E731
        if cnt(after) != cnt(before):
            raise RuntimeError(f"{p.name}: edit changed the resource count, refusing")
        p.write_text(new, encoding="utf-8")
        total += n
    return total


# ---- PR -------------------------------------------------------------------------------------------------------------

def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}: {(p.stderr or p.stdout).strip()[-300:]}")
    return p.stdout.strip()


def open_pr(f, lines, week):
    repo = paths.repo()
    if subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True).returncode:
        return f"no PR: {repo} has no origin (report only)"
    if subprocess.run(["gh", "auth", "status", "--hostname", "github.com"], capture_output=True).returncode:
        return "no PR: gh is not logged in for this user (report only)"
    branch = f"verify/{week}"
    wt = paths.state() / "verify-worktree"
    subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    shutil.rmtree(wt, ignore_errors=True)
    run(["git", "-C", str(repo), "fetch", "-q", "origin", "main"])
    run(["git", "-C", str(repo), "worktree", "add", "-q", "-B", branch, str(wt), "origin/main"])
    try:
        n = apply_edits(wt, f)
        (wt / "reports").mkdir(exist_ok=True)
        (wt / "reports" / f"verify-{week}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        run(["git", "add", "-A", "catalog", "reports"], cwd=wt)
        run(["git", "-c", "user.name=garage verify", "-c", "user.email=garage@localhost", "commit", "-q", "-m",
             f"verify {week}: {n} metadata updates, {len(f['archived'])} archived, {len(f['moved'])} moved, "
             f"{len(f['gone'])} gone"], cwd=wt)
        run(["git", "push", "-q", "--force-with-lease", "origin", branch], cwd=wt)
        url = run(["gh", "pr", "create", "--head", branch, "--base", "main", "--title", f"verify {week}",
                   "--body-file", str(wt / "reports" / f"verify-{week}.md")], cwd=wt)
        return f"PR {url}"
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garage verify", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="report only, no branch, no PR")
    g.add_argument("--pr", action="store_true", help="report + branch + PR (the weekly timer)")
    ap.add_argument("--out", help="report folder for --dry-run (default state/reports)")
    ap.add_argument("--no-lychee", action="store_true")
    ap.add_argument("--week", default=None, help="ISO week label, default this week")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    week = a.week or iso_week()
    cat, pins = catalog_mod.load(), pins_mod.load()
    f = sweep(cat, pins, lychee=not a.no_lychee)
    lines = report(f, week)
    st = paths.state()
    st.mkdir(parents=True, exist_ok=True)
    (st / f"verify-{week}.json").write_text(json.dumps(f, indent=1) + "\n", encoding="utf-8")
    out_dir = Path(a.out) if a.out else st / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = out_dir / f"verify-{week}.md"
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    status = "dry run: no branch, no PR" if a.dry_run else open_pr(f, lines, week)
    if a.json:
        print(json.dumps({"report": str(rep), "status": status, **{k: (len(v) if isinstance(v, list) else v)
                                                                  for k, v in f.items()}}, indent=1))
    else:
        print("\n".join(lines))
        print(f"\n{rep} · {status}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
