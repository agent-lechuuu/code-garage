"""Trust tiers of runnable items (skills, MCP servers, plugins, templates): quarantine -> reviewed -> trusted.

  tier(rid) -> "quarantine" | "reviewed" | "trusted" | "n/a"      (n/a = not runnable, no tier needed)
  allowed(rid, unattended=None) -> (bool, reason)                   unattended=None reads GARAGE_UNATTENDED=1
  effective(rid, rec=None, pin=None) -> (tier, reason)              what a record is worth against today's pin
  load(repo=None) -> {rid: record}    record(rid)    validate(registry) -> [errors]    put(rid, rec, why)    reset(rid)

trust/registry.yaml (schema/trust.schema.json): {rid: {trust, sha, scans: [{tool, version, date, result, findings}],
reviewed_by, reviewed, approved_by, approved, approval, notes, ...}}. Missing = quarantine. A record counts only while
its sha equals the pin's sha: a pin bump drops the item to quarantine until it is reviewed again. `trusted` counts only
with approved_by: owner and an approval id (the owner's tap, garage promote); no other code path writes it.
Rules for agents: GARAGE_UNATTENDED=1 -> trusted only; interactive -> reviewed or trusted ("reviewed, not yet trusted"
is said out loud); quarantine -> read-only data (garage show / grep), never added or loaded.
"""
import datetime as dt
import fcntl
import json
import os
import re
from pathlib import Path

from . import paths

TIERS = ("quarantine", "reviewed", "trusted")
RESULTS = ("pass", "warn", "fail", "skipped", "error")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CAN = ("shell", "network", "files", "secrets")
FIELDS = {"trust", "sha", "scans", "reviewed_by", "reviewed", "approved_by", "approved", "approval", "notes",
          "waivers", "summary", "can", "reasons", "kind", "history"}
HEADER = """\
# Code Garage trust registry: rid -> trust record (schema/trust.schema.json, rules in tools/garage/trust.py).
# Written by `garage review` (reviewed / quarantine) and `garage promote` (trusted, only with the owner's approval id).
# A record counts only while its sha equals lock/pins.yaml's sha for the rid. Missing = quarantine. Don't hand-edit
# `trusted`: CI (garage validate -> garage.policy) refuses it without approved_by: owner + approval.
"""

_cache = {}


def registry_file(repo=None):
    return Path(repo or paths.repo()) / "trust" / "registry.yaml"


def _norm(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    return v


def load(repo=None):
    """{rid: record} from trust/registry.yaml ({} when it doesn't exist; off-server: dist/catalog.json's trust)."""
    f = registry_file(repo)
    if f.is_file():
        key = (str(f), f.stat().st_mtime_ns, f.stat().st_size)
        if key not in _cache:
            import yaml
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                raise ValueError(f"{f}: not a mapping")
            _cache.clear()
            _cache[key] = {str(k): _norm(v) for k, v in data.items()}
        return _cache[key]
    from .catalog import dist_file
    dist = dist_file(repo)   # off-server: the repo's dist/ or the package's bundled copy, parsed once per mtime
    if dist:
        key = (str(dist), dist.stat().st_mtime_ns, dist.stat().st_size)
        if key not in _cache:
            with open(dist, encoding="utf-8") as fh:
                d = json.load(fh)
            reg = d.get("trust_registry")
            _cache.clear()
            _cache[key] = reg if isinstance(reg, dict) else {}
        return _cache[key]
    return {}


def _rid(rid):
    from .catalog import normalize_url
    return normalize_url(rid)


def record(rid, repo=None):
    reg = load(repo)
    return reg.get(rid) or reg.get(_rid(rid))


def _pin(rid):
    try:
        from . import pins
        return pins.get(rid)
    except ImportError:
        f = paths.repo() / "lock" / "pins.yaml"
        if not f.is_file():
            return None
        import yaml
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        return data.get(rid) or data.get(_rid(rid))


def _resource(rid):
    try:
        from . import catalog
        res = catalog.load()["resources"]
    except Exception:   # noqa: BLE001 - no catalog: treat the item as runnable (the safe side)
        return None
    return res.get(rid) or res.get(_rid(rid))


def is_runnable(res):
    from .catalog import is_runnable as f
    return f(res)


def record_errors(rid, rec):
    """Shape and rule errors of one record (schema/trust.schema.json, without a jsonschema dependency)."""
    e = []
    if not isinstance(rec, dict):
        return [f"{rid}: not a mapping"]
    rec = _norm(rec)
    for k in sorted(set(rec) - FIELDS):
        e.append(f"{rid}: unknown field {k}")
    t = rec.get("trust")
    if t not in TIERS:
        e.append(f"{rid}: trust must be one of {', '.join(TIERS)}")
    if not SHA_RE.match(str(rec.get("sha", ""))):
        e.append(f"{rid}: sha must be the full 40-hex commit id")
    scans = rec.get("scans", [])
    if not isinstance(scans, list):
        e.append(f"{rid}: scans must be a list")
        scans = []
    for i, s in enumerate(scans):
        if not isinstance(s, dict) or not s.get("tool") or s.get("result") not in RESULTS \
                or not isinstance(s.get("findings", 0), int) or not DATE_RE.match(str(s.get("date", ""))):
            e.append(f"{rid}: scans[{i}] needs tool, version, date YYYY-MM-DD, result {'|'.join(RESULTS)}, "
                     "findings int")
    for k in ("reviewed", "approved"):
        if rec.get(k) is not None and not DATE_RE.match(str(rec[k])):
            e.append(f"{rid}: {k} must be YYYY-MM-DD")
    for w in rec.get("waivers") or []:
        if not (isinstance(w, dict) and w.get("tool") and str(w.get("reason", "")).strip()):
            e.append(f"{rid}: every waiver needs a tool and a reason")
    can = rec.get("can")
    if can is not None and (not isinstance(can, dict) or set(can) - set(CAN)
                            or not all(isinstance(v, bool) for v in can.values())):
        e.append(f"{rid}: can must map {', '.join(CAN)} to true/false")
    if t in ("reviewed", "trusted"):
        if not rec.get("reviewed_by") or not rec.get("reviewed"):
            e.append(f"{rid}: {t} needs reviewed_by and reviewed (the review record)")
        if not scans:
            e.append(f"{rid}: {t} needs the scans it passed")
    if t == "trusted":
        if rec.get("approved_by") != "owner":
            e.append(f"{rid}: trusted without approved_by: owner")
        a = rec.get("approval")
        if not (isinstance(a, int) and not isinstance(a, bool) and a > 0):
            e.append(f"{rid}: trusted without an approval id (the owner's tap, garage promote)")
        if not rec.get("approved"):
            e.append(f"{rid}: trusted without the approval date")
    elif rec.get("approved_by") or rec.get("approval"):
        e.append(f"{rid}: approved_by/approval only belong to trusted records")
    return e


def validate(registry):
    if not isinstance(registry, dict):
        return ["trust registry: not a mapping"]
    out = []
    for rid, rec in registry.items():
        if not re.match(r"^https?://", str(rid)):
            out.append(f"{rid}: key is not a URL")
        out += record_errors(rid, rec)
    return out


def effective(rid, rec=None, pin=None):
    """(tier, reason) of a runnable item: the record's tier only while it is valid and bound to today's pin."""
    rec = rec if rec is not None else record(rid)
    pin = pin if pin is not None else _pin(rid)
    if not rec:
        return "quarantine", "no review yet"
    t = rec.get("trust")
    if t == "quarantine":
        why = "; ".join(rec.get("reasons") or []) or rec.get("notes") or "kept in quarantine by its review"
        return "quarantine", str(why)[:300]
    if not pin or not pin.get("sha"):
        return "quarantine", "not pinned (no lock/pins.yaml entry)"
    if rec.get("sha") != pin.get("sha"):
        return "quarantine", (f"the review is for {str(rec.get('sha'))[:12]}, the pin is now {pin['sha'][:12]}: "
                              "needs a new review")
    errs = record_errors(rid, rec)
    if errs:
        return "quarantine", f"invalid trust record ({errs[0].split(': ', 1)[-1]})"
    if t == "trusted":
        return "trusted", f"trusted (owner approval #{rec['approval']}, {rec['approved']})"
    return "reviewed", f"reviewed by {rec.get('reviewed_by')} on {rec.get('reviewed')}, not yet trusted"


def tier(rid):
    res = _resource(rid)
    if res is not None and not is_runnable(res):
        return "n/a"
    return effective(rid)[0]


def unattended_env():
    return os.environ.get("GARAGE_UNATTENDED", "") == "1"


def allowed(rid, unattended=None):
    """May this item be added/loaded? Interactive: reviewed or trusted. Unattended: trusted only. Quarantine: never."""
    if unattended is None:
        unattended = unattended_env()
    res = _resource(rid)
    if res is not None and not is_runnable(res):
        return True, "not runnable code (docs/reference): no trust tier needed"
    t, why = effective(rid)
    if t == "trusted":
        return True, why
    if t == "reviewed":
        if unattended:
            return False, (f"{why}; unattended runs (GARAGE_UNATTENDED=1) may only use trusted items: "
                           "the owner promotes reviewed items weekly")
        return True, f"{why}: say 'reviewed, not yet trusted' when you use it"
    return False, (f"quarantine ({why}): read-only data until reviewed. Read it with `garage show` / `garage grep`; "
                   "never copy, run or load it")


# ---- writing (garage review / promote) -----------------------------------------------------------------------------

def _dump(reg):
    import yaml
    body = yaml.safe_dump({k: reg[k] for k in sorted(reg)}, sort_keys=False, allow_unicode=True, width=118,
                          default_flow_style=False) if reg else "{}\n"
    return HEADER + "\n" + body


def log_event(event):
    """Append-only trail in $GARAGE_HOME/state/trust-log.jsonl (survives a repo reset)."""
    try:
        d = paths.state()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "trust-log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": dt.datetime.now().astimezone().isoformat(timespec="seconds"), **event},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def update(changes, why, repo=None, allow_trusted=False):
    """Apply {rid: record|None} under a lock, validate, write atomically. Only promote passes allow_trusted=True."""
    f = registry_file(repo)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f.with_suffix(".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        _cache.clear()
        reg = dict(load(repo)) if f.is_file() else {}
        for rid, rec in changes.items():
            old = reg.get(rid)
            if rec is None:
                reg.pop(rid, None)
                continue
            rec = {k: v for k, v in _norm(rec).items() if v not in (None, "", [], {})}
            if rec.get("trust") == "trusted" and not (allow_trusted and old is not None):
                raise PermissionError(f"{rid}: only `garage promote` with an owner approval writes trusted")
            errs = record_errors(rid, rec)
            if errs:
                raise ValueError("; ".join(errs))
            reg[rid] = rec
        tmp = f.with_suffix(".yaml.tmp")
        tmp.write_text(_dump(reg), encoding="utf-8")
        os.chmod(tmp, 0o644)
        tmp.replace(f)
        _cache.clear()
    for rid, rec in changes.items():
        log_event({"rid": rid, "trust": (rec or {}).get("trust", "removed"), "sha": (rec or {}).get("sha"),
                   "why": why})


def put(rid, rec, why, repo=None):
    update({rid: rec}, why, repo)


def reset(rid, reason="pin moved", repo=None):
    """For pin bumps: the record drops to quarantine (history kept in notes); a no-op without a record."""
    rec = record(rid, repo)
    if not rec or rec.get("trust") == "quarantine":
        return
    hist = list(rec.get("history") or [])[-4:] + [f"{dt.date.today()}: was {rec['trust']} at "
                                                  f"{str(rec.get('sha'))[:12]}; {reason}"]
    put(rid, {"trust": "quarantine", "sha": rec["sha"], "reasons": [reason], "history": hist}, f"reset: {reason}",
        repo)


def health():
    try:
        reg = load()
    except Exception as e:   # noqa: BLE001 - doctor reports, never raises
        return [("FAIL", f"trust: {e}")]
    errs = validate(reg)
    counts = {t: 0 for t in TIERS}
    stale = 0
    for rid, rec in reg.items():
        t, _ = effective(rid, rec)
        counts[t] += 1
        pin = _pin(rid)
        if rec.get("trust") != "quarantine" and pin and pin.get("sha") != rec.get("sha"):
            stale += 1
    line = f"trust: {len(reg)} records ({', '.join(f'{k} {v}' for k, v in counts.items())})"
    out = [("FAIL" if errs else "PASS", line + (f"; {len(errs)} errors, first: {errs[0]}" if errs else ""))]
    if stale:
        out.append(("WAIT", f"trust: {stale} reviews are for an older pin (re-review: garage review ID)"))
    return out
