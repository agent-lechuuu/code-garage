"""The lock file lock/pins.yaml: one pinned commit per GitHub resource (machine-written by `garage pin`).

  {rid: {repo: owner/name, sha: <40 hex>, path: "<sub-folder or ''>", pinned: YYYY-MM-DD,
         license_at_pin: SPDX, size_kb: int, policy: snapshot|readme|link}}

  get(rid) -> dict|None      all() -> {rid: pin}      validate(pins) -> [error strings]
  policy_for(res, license_at_pin, size_kb, path)      the mirror policy (frozen contract, BUILD.md)
  graphql_repos(repos)       GitHub metadata, 50 repos per GraphQL call through `gh` (research/ghmeta.py's method)

Non-GitHub resources have no pin (policy "link" is implied). Off-server without lock/pins.yaml, the pins come from
dist/catalog.json (each resource's "pin", as T1's `garage build` writes it).
size_kb is GitHub's diskUsage (the repository with its history, in KB): only a coarse "giant repo" signal.
"""
import json
import os
import re
import subprocess
from pathlib import Path

from . import paths

FIELDS = ("repo", "sha", "path", "pinned", "license_at_pin", "size_kb", "policy")
POLICIES = ("snapshot", "readme", "link")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GIANT_KB = 500_000            # diskUsage above this (history included) and no `path`: README + docs only
NO_LICENCE = {"", "none"}     # NOASSERTION/OTHER = a licence file GitHub can't name: mirrored, never vendored
SNAPSHOT_USE = {"vendor", "template"}
BATCH = 50
# github.com/<these>/... are site pages, not repositories
RESERVED_OWNERS = {"topics", "orgs", "sponsors", "marketplace", "collections", "features", "apps", "settings",
                   "enterprise", "about", "site", "trending", "explore", "customer-stories", "solutions", "readme",
                   "resources", "events", "login", "search", "pricing", "security", "advisories"}
GQL_FIELDS = """
  nameWithOwner isArchived isFork diskUsage pushedAt stargazerCount
  licenseInfo { spdxId }
  defaultBranchRef { name target { oid } }
"""

_cache = {}


def lock_file(repo=None):
    return Path(repo or paths.repo()) / "lock" / "pins.yaml"


def _norm(pin):
    pin = dict(pin)
    for k, v in pin.items():
        if hasattr(v, "isoformat"):
            pin[k] = v.isoformat()
    return pin


def load(repo=None):
    """{rid: pin} from lock/pins.yaml, else from dist/catalog.json (off-server), else {}."""
    f = lock_file(repo)
    if f.is_file():
        key = (str(f), f.stat().st_mtime_ns)
        if key not in _cache:
            import yaml
            loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)   # libyaml: ~0.2 s instead of ~2 s
            with open(f, encoding="utf-8") as fh:
                data = yaml.load(fh, Loader=loader) or {}
            _cache.clear()
            _cache[key] = {rid: _norm(p) for rid, p in data.items()}
        return _cache[key]
    from .catalog import dist_file
    dist = dist_file(repo)   # off-server: the repo's dist/, or the copy bundled in the package
    if dist:
        key = (str(dist), dist.stat().st_mtime_ns, dist.stat().st_size)
        if key not in _cache:
            with open(dist, encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d.get("pins"), dict):
                got = d["pins"]
            else:
                res = d.get("resources") or {}
                got = {rid: r["pin"] for rid, r in res.items()
                       if isinstance(r, dict) and isinstance(r.get("pin"), dict)}
            _cache.clear()
            _cache[key] = got
        return _cache[key]
    return {}


def all():   # noqa: A001 - frozen contract name
    return load()


def get(rid):
    from .catalog import normalize_url
    p = load()
    return p.get(rid) or p.get(normalize_url(rid))


def dump(pins, repo=None):
    """Write lock/pins.yaml: sorted, one flow mapping per line (small diffs on pin bumps)."""
    f = lock_file(repo)
    f.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Machine-written by `garage pin` (tools/garage/pin.py). Schema: schema/pins.schema.json.",
             "# Pins never move on their own: `garage pin --outdated` lists upstream movement, `--bump` moves one.", ""]
    for rid in sorted(pins):
        p = pins[rid]
        body = ", ".join(f"{k}: {json.dumps(p[k])}" for k in FIELDS)
        lines.append(f"{json.dumps(rid)}: {{{body}}}")
    tmp = f.with_suffix(".yaml.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(f)
    _cache.clear()


def validate(pins):
    """The checks of schema/pins.schema.json, without a jsonschema dependency."""
    errs = []
    if not isinstance(pins, dict):
        return ["pins: not a mapping"]
    for rid, p in pins.items():
        if not re.match(r"^https?://", str(rid)):
            errs.append(f"{rid}: key is not a URL")
        if not isinstance(p, dict):
            errs.append(f"{rid}: not a mapping")
            continue
        p = _norm(p)
        missing = [k for k in FIELDS if k not in p]
        extra = [k for k in p if k not in FIELDS]
        if missing:
            errs.append(f"{rid}: missing {', '.join(missing)}")
        if extra:
            errs.append(f"{rid}: unknown {', '.join(extra)}")
        if "sha" in p and not SHA_RE.match(str(p["sha"])):
            errs.append(f"{rid}: sha is not 40 lowercase hex")
        if "repo" in p and not REPO_RE.match(str(p["repo"])):
            errs.append(f"{rid}: repo is not owner/name")
        if "pinned" in p and not DATE_RE.match(str(p["pinned"])):
            errs.append(f"{rid}: pinned is not YYYY-MM-DD")
        if "policy" in p and p["policy"] not in POLICIES:
            errs.append(f"{rid}: policy not in {POLICIES}")
        if "size_kb" in p and (not isinstance(p["size_kb"], int) or isinstance(p["size_kb"], bool)
                               or p["size_kb"] < 0):
            errs.append(f"{rid}: size_kb is not a non-negative int")
        if "path" in p and (not isinstance(p["path"], str) or p["path"].startswith("/") or ".." in
                            p["path"].split("/")):
            errs.append(f"{rid}: path must be relative, without ..")
        if "license_at_pin" in p and not (isinstance(p["license_at_pin"], str) and p["license_at_pin"]):
            errs.append(f"{rid}: license_at_pin is empty")
    return errs


def effective_license(license_at_pin, catalog_license=None):
    """GitHub's SPDX id, or the catalog's (hand-corrected per folder) when GitHub found none/NOASSERTION."""
    g = str(license_at_pin or "")
    if g.lower() not in NO_LICENCE | {"noassertion", "other"}:
        return g
    c = str(catalog_license or "")
    if c.lower() not in NO_LICENCE | {"noassertion", "other"}:
        return c
    return g or c or "none"


def policy_for(res, license_at_pin, size_kb, path):
    """snapshot | readme | link for one resource (BUILD.md, frozen contract)."""
    from .catalog import is_runnable
    lic = effective_license(license_at_pin, res.get("license"))
    if lic.lower() in NO_LICENCE:
        return "link"
    if is_runnable(res) or res.get("use") in SNAPSHOT_USE:
        if (size_kb or 0) > GIANT_KB and not path:
            return "readme"
        return "snapshot"
    return "readme"


def repo_of(url):
    """('owner/name', 'sub/path') for a GitHub repository URL, else None."""
    from .catalog import github_repo
    r = github_repo(url)
    if not r:
        return None
    repo, sub = r
    if repo.split("/")[0].lower() in RESERVED_OWNERS:
        return None
    return repo, sub


def path_of(res):
    """The sub-folder that matters: the URL's /tree|blob/<ref>/<path>, else the resource's `path`."""
    r = repo_of(res.get("url", ""))
    sub = (r[1] if r else "") or str(res.get("path") or "")
    return sub.strip("/")


# ---- GitHub GraphQL -------------------------------------------------------------------------------------------------

def _gh_graphql(query):
    p = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"], capture_output=True, text=True,
                       timeout=180)
    try:
        return json.loads(p.stdout or "{}").get("data") or {}, p.stderr.strip()[:300]
    except json.JSONDecodeError:
        return {}, (p.stderr or p.stdout).strip()[:300]


def graphql_repos(repos, fields=GQL_FIELDS, log=None):
    """{repo (as asked): node|None}. None = not found / no access. 50 per call; a failed call is retried as two halves.

    GARAGE_GH_FIXTURE=<file.json> ({"owner/name": node|null}) replaces GitHub (tests, dry runs)."""
    fx = os.environ.get("GARAGE_GH_FIXTURE")
    if fx:
        with open(fx, encoding="utf-8") as f:
            data = json.load(f)
        low = {k.lower(): v for k, v in data.items()}
        return {r: low.get(r.lower()) for r in repos}
    out = {}
    calls = 0

    def run(batch):
        nonlocal calls
        parts = []
        for i, full in enumerate(batch):
            owner, _, name = full.partition("/")
            parts.append(f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{{fields}}}")
        calls += 1
        data, err = _gh_graphql("query {" + "\n".join(parts) + "}")
        if not data and len(batch) > 1:
            if log:
                log(f"graphql call failed ({err}); retrying {len(batch)} repos as two halves")
            half = len(batch) // 2
            run(batch[:half])
            run(batch[half:])
            return
        for i, full in enumerate(batch):
            out[full] = data.get(f"r{i}")

    uniq = list(dict.fromkeys(repos))
    for i in range(0, len(uniq), BATCH):
        run(uniq[i:i + BATCH])
    if log:
        log(f"graphql: {len(uniq)} repos in {calls} calls")
    return out


def head_of(node):
    ref = (node or {}).get("defaultBranchRef") or {}
    return (ref.get("target") or {}).get("oid"), ref.get("name")


def spdx_of(node):
    return ((node or {}).get("licenseInfo") or {}).get("spdxId") or "none"


def health():
    f = lock_file()
    if not f.is_file():
        return [("WAIT", f"pins: no {f} yet (run `garage pin`)")]
    try:
        p = load()
    except Exception as e:   # noqa: BLE001 - doctor reports, never raises
        return [("FAIL", f"pins: {e}")]
    errs = validate(p)
    pol = {k: sum(1 for x in p.values() if x.get("policy") == k) for k in POLICIES}
    return [("FAIL" if errs else "PASS",
             f"pins: {len(p)} ({', '.join(f'{k} {v}' for k, v in pol.items())})"
             + (f"; {len(errs)} errors, first: {errs[0]}" if errs else ""))]
