"""`garage review`: scan results + a reviewer's checklist (docs/safety.md) -> `reviewed`, or `quarantine` with reasons.

  garage review ID                      scan the pinned snapshot if there is no report for this sha, print the brief
  garage review ID --verdict reviewed|quarantine --by NAME --notes TEXT [--summary TEXT] [--can shell,network,...]
                   [--waive TOOL=REASON ...] [--checklist FILE] [--rescan]
                                        record an interactive review (a person or a builder session)
  garage review --pending [--json]      runnable, pinned, mirrored items without a review for their pinned sha
  garage review --check                 exit 0 if anything is pending, 1 if not (lechu-job pre-check: no Claude call)
  garage review --facts [--limit 3]     for the weekly AI job: scan up to N pending items, print what to read and
                                        where to write the verdict ($GARAGE_HOME/state/review-inbox/)
  garage review --ingest [--dry-run]    apply the job's verdicts (stricter: it can't waive a failed scanner)

Never writes `trusted` (only `garage promote`, with the owner's approval). The gate for `reviewed`: a scan of the
pinned sha in which every required scanner ran, no failed scanner without a waiver, a reviewer name and notes.
Every recorded verdict is committed and pushed (trust/registry.yaml only) when $GARAGE_REPO is a git clone: trustgit.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

from . import paths, scan
from . import trust as trust_mod

CHECKLIST = [f"C{i}" for i in range(1, 26)]
JOB_REVIEWER = "garage-review job (sonnet)"
JOB_UNTESTABLE = {"C23"}   # the job has no shell: the sandboxed first run is for a person


def today():
    return dt.date.today().isoformat()


def inbox():
    return paths.state() / "review-inbox"


def review_file(rid, sha):
    return paths.state() / "reviews" / scan.slug(rid) / f"{sha[:12]}.json"


def _pins():
    from . import pins
    return pins


def _cat():
    from . import catalog
    return catalog


def _write_json(f, data):
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def gate(rid, rep, pin, waivers, unattended):
    """Reasons that keep the item out of `reviewed` (empty = the scan side is fine)."""
    reasons = []
    if not pin:
        return ["not pinned"]
    if not rep:
        return [f"no scan of {pin['sha'][:12]} (garage scan {rid})"]
    if rep.get("sha") != pin["sha"]:
        return [f"the scan is of {str(rep.get('sha'))[:12]}, the pin is {pin['sha'][:12]}: scan again"]
    if not rep.get("complete"):
        reasons.append("required scanners did not run: " + ", ".join(rep.get("missing") or []))
    waived = {w["tool"] for w in waivers}
    for r in rep["scanners"]:
        if r["result"] != "fail":
            continue
        top = r["details"][0] if r["details"] else {}
        where = f"{top.get('file')}:{top.get('line')}" if top.get("line") else str(top.get("file") or "")
        what = f"{r['tool']} failed ({r['findings']} findings; first: {top.get('rule')} {where})"
        if r["tool"] not in waived:
            reasons.append(what)
        elif unattended:
            reasons.append(what + ": the job's proposed waiver needs an interactive reviewer")
    return reasons


def record_review(rid, verdict, by, notes, rep, pin, summary="", can=None, waivers=(), checklist=None,
                  reasons=(), unattended=False, dry_run=False, extra=None):
    """Write the full review to state/reviews/ and the short record to trust/registry.yaml. -> the record."""
    if verdict not in ("reviewed", "quarantine"):
        raise ValueError("verdict must be reviewed or quarantine (only garage promote makes items trusted)")
    if not by or not str(notes or "").strip():
        raise ValueError("a review needs --by and --notes")
    waivers = [{"tool": w["tool"], "reason": str(w["reason"]).strip()[:300]} for w in waivers]
    if any(not w["reason"] for w in waivers):
        raise ValueError("every waiver needs a reason")
    reasons = list(reasons)
    if checklist:
        fails = [f"{k}: {v}" for k, v in checklist.items() if str(v).strip().lower().startswith("fail")]
        reasons += fails
    gate_reasons = gate(rid, rep, pin, waivers, unattended)
    trust = "reviewed" if verdict == "reviewed" and not gate_reasons and not reasons else "quarantine"
    if verdict == "quarantine" and not reasons:
        reasons.append(str(notes).strip()[:300])
    old = trust_mod.record(rid)
    if old and old.get("trust") == "trusted" and old.get("sha") == pin["sha"] and trust == "reviewed":
        return old   # already trusted for this sha: a re-review that passes changes nothing
    rec = {"trust": trust, "sha": pin["sha"], "scans": scan.registry_scans(rep) if rep else [],
           "reviewed_by": by, "reviewed": today(), "notes": str(notes).strip()[:600],
           "summary": str(summary or "").strip()[:200], "can": can or (rep or {}).get("capabilities"),
           "waivers": [w for w in waivers if not unattended] or None,
           "reasons": (gate_reasons + reasons)[:8] if trust == "quarantine" else None,
           "kind": (rep or {}).get("kind")}
    full = {"rid": rid, "sha": pin["sha"], "date": today(), "by": by, "verdict_asked": verdict, "result": trust,
            "reasons": gate_reasons + reasons, "notes": notes, "summary": summary, "can": rec["can"],
            "waivers": waivers, "checklist": checklist, "unattended": unattended, "scan_report": (rep or {}).get(
                "report") or str(scan.report_file(rid, pin["sha"])), **(extra or {})}
    if dry_run:
        return {k: v for k, v in rec.items() if v is not None}
    _write_json(review_file(rid, pin["sha"]), full)
    trust_mod.put(rid, rec, f"review by {by}: {trust}")
    written = trust_mod.record(rid)
    from . import trustgit
    trustgit.publish({rid: written}, trustgit.message([rid], trust, by))
    return written


def pending(limit=None):
    """[(rid, res, pin, snapshot dir)] runnable items whose pinned sha has no review yet, best first."""
    catalog = _cat()
    cat = catalog.load()
    pins = _pins().all()
    reg = trust_mod.load()
    out = []
    for rid, res in cat["resources"].items():
        if not catalog.is_runnable(res):
            continue
        pin = pins.get(rid)
        if not pin or pin.get("policy") != "snapshot":
            continue
        rec = reg.get(rid)
        if rec and rec.get("sha") == pin["sha"]:
            continue   # reviewed (or kept in quarantine by a review) for this exact commit
        d = scan.snapshot(rid, pin)
        if d:
            out.append((rid, res, pin, d))
    out.sort(key=lambda x: (int(x[1].get("tier") or 3), -int(x[1].get("stars") or 0), x[0]))
    return out[:limit] if limit else out


def _report(rid, pin, rescan=False):
    rep = None if rescan else scan.last_report(rid, pin["sha"])
    return rep or scan.scan_item(rid)


def brief(rid, res, pin, rep):
    t, why = trust_mod.effective(rid)
    lines = [f"{(res or {}).get('name') or rid}  [{t}: {why}]", f"  rid  {rid}", f"  sha  {pin['sha']}  "
             f"(pinned {pin.get('pinned')}, licence {pin.get('license_at_pin')}, catalog {(res or {}).get('license')})",
             f"  snapshot  {rep.get('target')}"]
    lines += scan.summary_lines(rep, top=6)
    lines.append(f"  checklist: {paths.repo() / 'docs' / 'safety.md'} (C1-C25)")
    return lines


def parse_waivers(items):
    out = []
    for w in items or []:
        tool, sep, reason = w.partition("=")
        if not sep or not reason.strip():
            raise ValueError(f"--waive {w!r}: use TOOL=REASON")
        out.append({"tool": tool.strip(), "reason": reason.strip()})
    return out


def load_checklist(path):
    if not path:
        return None
    import yaml
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("--checklist: a mapping {C1: ok, ...}")
    return {str(k).upper(): str(v) for k, v in data.items()}


def cmd_interactive(a):
    rid, res = scan.resolve(a.id)
    pin = _pins().get(rid)
    if not pin:
        print(f"garage review: {rid} is not pinned (garage pin first)", file=sys.stderr)
        return 2
    try:
        rep = _report(rid, pin, a.rescan)
    except LookupError as e:
        print(f"garage review: {e}", file=sys.stderr)
        return 2
    if not a.verdict:
        out = brief(rid, res, pin, rep)
        out.append(f"  record: garage review {rid} --verdict reviewed|quarantine --by NAME --notes '...' "
                   "[--summary '...'] [--can shell,network,files,secrets] [--waive TOOL=REASON]")
        print("\n".join(out))
        return 0
    can = None
    if a.can is not None:
        bad = {c for c in a.can.split(",") if c} - set(trust_mod.CAN)
        if bad:
            print(f"garage review: --can takes {', '.join(trust_mod.CAN)}", file=sys.stderr)
            return 2
        can = {c: c in a.can.split(",") for c in trust_mod.CAN}
    try:
        rec = record_review(rid, a.verdict, a.by, a.notes, rep, pin, a.summary, can, parse_waivers(a.waive),
                            load_checklist(a.checklist), dry_run=a.dry_run)
    except (ValueError, PermissionError) as e:
        print(f"garage review: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(rec, indent=1, ensure_ascii=False))
    else:
        print(f"{rid}: {rec['trust']}" + ("" if rec["trust"] != "quarantine" else
                                          " — " + "; ".join(rec.get("reasons") or [])[:400])
              + (" (dry run, nothing written)" if a.dry_run else ""))
    return 0 if rec["trust"] == a.verdict or a.verdict == "quarantine" else 1


VERDICT_SHAPE = """{"rid": "<rid>", "sha": "<40-hex sha>", "verdict": "reviewed" | "quarantine",
 "summary": "<one line: what it is>", "can": {"shell": bool, "network": bool, "files": bool, "secrets": bool},
 "checklist": {"C1": "ok" | "n/a" | "fail: <why>", ... every C1..C25},
 "reasons": ["<why it stays in quarantine>"], "waivers": [{"tool": "<scanner>", "reason": "<file:line, why harmless>"}],
 "notes": "<what you read, the findings you opened and what they were>"}"""


def cmd_facts(a):
    items = pending()
    if not items:
        print("Nothing to review.")
        return 0
    start, shown = time.monotonic(), 0
    print(f"{len(items)} runnable items wait for a review; here are up to {a.limit}. Checklist: "
          f"{paths.repo() / 'docs' / 'safety.md'}.\nWrite one verdict per item to {inbox()}/<file named below>, "
          f"as JSON:\n{VERDICT_SHAPE}\n")
    for rid, res, pin, d in items:
        if shown >= a.limit or time.monotonic() - start > a.budget:
            break
        try:
            rep = _report(rid, pin)
        except LookupError as e:
            print(f"## {rid}\n  skipped: {e}\n")
            continue
        shown += 1
        print(f"## {shown}. verdict file: {inbox()}/{scan.slug(rid)}-{pin['sha'][:12]}.json")
        print("\n".join(brief(rid, res, pin, rep)))
        print(f"  catalog note: {(res or {}).get('note', '')}")
        files = sorted(p for p in scan._walk(Path(rep["target"])))[:80]
        print("  files (read every instruction file in full):")
        for p in files:
            try:
                print(f"    {p.relative_to(rep['target'])}  {p.stat().st_size} B")
            except OSError:
                pass
        print()
    if shown < len(items):
        print(f"({len(items) - shown} more wait for next week or an interactive reviewer.)")
    return 0


def _valid_verdict(v, pins):
    rid = v.get("rid")
    pin = pins.get(rid) if isinstance(rid, str) else None
    if not pin:
        return None, "unknown or unpinned rid"
    if v.get("sha") != pin["sha"]:
        return None, f"sha {str(v.get('sha'))[:12]} is not the pin {pin['sha'][:12]}"
    if v.get("verdict") not in ("reviewed", "quarantine"):
        return None, "verdict must be reviewed or quarantine"
    cl = {str(k).upper(): str(x) for k, x in (v.get("checklist") or {}).items()}
    missing = [c for c in CHECKLIST if c not in cl]
    if missing:
        return None, f"checklist incomplete: {', '.join(missing[:6])}"
    bad = [c for c in CHECKLIST if not re.match(r"^\s*(ok|n/a|fail)\b", cl[c], re.I)]
    if bad:
        return None, f"checklist answers must start with ok, n/a or fail: {', '.join(bad[:6])}"
    can = v.get("can") or {}
    if not isinstance(can, dict) or not all(isinstance(can.get(k), bool) for k in trust_mod.CAN):
        return None, "can needs shell/network/files/secrets as true/false"
    return pin, cl


def cmd_ingest(a):
    pins = _pins().all()
    d = inbox()
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    if not files:
        print("No verdicts waiting.")
        return 0
    done = d / "done"
    n = 0
    for f in files:
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"{f.name}: unreadable ({e})")
            continue
        pin, cl = _valid_verdict(v if isinstance(v, dict) else {}, pins)
        if not pin:
            print(f"{f.name}: rejected: {cl}")
            if not a.dry_run:
                done.mkdir(exist_ok=True)
                f.replace(done / (f.stem + ".rejected.json"))
            continue
        rid = v["rid"]
        rep = scan.last_report(rid, pin["sha"])
        for c in JOB_UNTESTABLE:
            cl[c] = cl[c] if cl[c].lower().startswith("fail") else "n/a (job has no shell)"
        try:
            waivers = [{"tool": str(w["tool"]), "reason": str(w["reason"])} for w in v.get("waivers") or []
                       if isinstance(w, dict) and w.get("tool") and w.get("reason")]
            rec = record_review(rid, v["verdict"], JOB_REVIEWER, str(v.get("notes") or v.get("summary") or "-"),
                                rep, pin, str(v.get("summary") or ""), {k: bool(v["can"][k]) for k in trust_mod.CAN},
                                waivers, cl, [str(x)[:200] for x in v.get("reasons") or []], unattended=True,
                                dry_run=a.dry_run, extra={"verdict_file": f.name})
        except (ValueError, PermissionError) as e:
            print(f"{f.name}: rejected: {e}")
            continue
        n += 1
        print(f"{rid}: {rec['trust']}" + (" — " + "; ".join(rec.get("reasons") or [])[:300]
                                          if rec["trust"] == "quarantine" else ""))
        if not a.dry_run:
            done.mkdir(exist_ok=True)
            f.replace(done / f.name)
    print(f"{n} verdicts applied" + (" (dry run)" if a.dry_run else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garage review", description=__doc__.split("\n")[0])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--verdict", choices=["reviewed", "quarantine"])
    ap.add_argument("--by", default=os.environ.get("GARAGE_REVIEWER", ""))
    ap.add_argument("--notes", default="")
    ap.add_argument("--summary", default="")
    ap.add_argument("--can", help="comma list of shell,network,files,secrets (default: what the scan found)")
    ap.add_argument("--waive", action="append", metavar="TOOL=REASON")
    ap.add_argument("--checklist", metavar="FILE", help="YAML/JSON {C1: ok, ..., C25: ok}")
    ap.add_argument("--rescan", action="store_true")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--budget", type=int, default=100,
                    help="--facts starts no new scan after this many seconds (lechu-job kills facts at 300 s)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.check:
            return 0 if pending(limit=1) else 1
        if a.pending:
            items = pending()
            if a.json:
                print(json.dumps([{"rid": r, "name": res.get("name"), "sha": p["sha"], "snapshot": str(d)}
                                  for r, res, p, d in items], indent=1))
            else:
                for r, res, p, d in items:
                    print(f"{p['sha'][:12]}  {res.get('name')}  {r}")
                print(f"{len(items)} pending", file=sys.stderr)
            return 0
        if a.facts:
            return cmd_facts(a)
        if a.ingest:
            return cmd_ingest(a)
        if not a.id:
            ap.error("give an ID, or --pending/--check/--facts/--ingest")
        return cmd_interactive(a)
    except (LookupError, FileNotFoundError) as e:
        print(f"garage review: {e}", file=sys.stderr)
        return 2


def health():
    try:
        n = len(pending())
    except Exception as e:   # noqa: BLE001 - doctor reports, never raises
        return [("WAIT", f"review: pending list unavailable ({e})")]
    d = inbox()
    waiting = len(list(d.glob("*.json"))) if d.is_dir() else 0
    return [("PASS", f"review: {n} items wait for a review" + (f", {waiting} job verdicts to ingest" if waiting
                                                               else ""))]


if __name__ == "__main__":
    sys.exit(main())
