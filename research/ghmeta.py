#!/usr/bin/env python3
"""Batch GitHub repo metadata for the garage research.

Usage: python3 -I ghmeta.py owner/repo [owner/repo ...]   (or one per line on stdin)
Prints one JSON object per repo: repo, license (SPDX), stars, pushed (YYYY-MM-DD),
archived, fork, description, default_branch, or "error" when GitHub can't find it.
Uses `gh api graphql` (the server's login), 50 repos per request.
"""
import json
import subprocess
import sys

FIELDS = """
  nameWithOwner stargazerCount pushedAt isArchived isFork description
  licenseInfo { spdxId } defaultBranchRef { name }
"""


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def query(batch):
    parts = []
    for i, full in enumerate(batch):
        owner, _, name = full.partition("/")
        parts.append(f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{{FIELDS}}}')
    q = "query {" + "\n".join(parts) + "}"
    p = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True)
    try:
        data = json.loads(p.stdout or "{}").get("data") or {}
    except json.JSONDecodeError:
        data = {}
    for i, full in enumerate(batch):
        r = data.get(f"r{i}")
        if not r:
            print(json.dumps({"repo": full, "error": "not found or no access"}))
            continue
        print(json.dumps({
            "repo": r["nameWithOwner"],
            "license": (r.get("licenseInfo") or {}).get("spdxId") or "none",
            "stars": r["stargazerCount"],
            "pushed": (r.get("pushedAt") or "")[:10],
            "archived": r["isArchived"],
            "fork": r["isFork"],
            "description": (r.get("description") or "")[:160],
            "default_branch": (r.get("defaultBranchRef") or {}).get("name"),
        }))


def main():
    args = sys.argv[1:] or [l.strip() for l in sys.stdin if l.strip()]
    repos = []
    for a in args:
        a = a.removeprefix("https://github.com/").removeprefix("github.com/").strip("/")
        a = "/".join(a.split("/")[:2]).removesuffix(".git")
        if a.count("/") == 1 and a not in repos:
            repos.append(a)
    for batch in chunks(repos, 50):
        query(batch)


if __name__ == "__main__":
    main()
