"""`garage promote`: the owner's weekly card. Reviewed items become trusted only with the owner's approval.

  garage promote --propose [--dry-run] [--json]   one card listing every `reviewed` item (what it is, what it can do,
                                                  the scan summary), sent through the server's approval broker
                                                  (lechu-ask garage.promote: app / Telegram buttons, 30 min to answer);
                                                  on Approve every item on the card is recorded `trusted`
  garage promote --record-approval ID             apply an approval given earlier (e.g. after an interrupted run)
  garage promote --list                           the reviewed items that would go on the card

An approval counts only if the broker confirms it (`lechu-ask --status ID`: kind garage.promote, decision approved)
and the card it approved carries this proposal's fingerprint (the exact rids and commits). Each item must still be
`reviewed` at the same sha when it is written. Records get approved_by: owner, approved: date, approval: ID, and
trust/registry.yaml (only that file) is committed and pushed when $GARAGE_REPO is a git clone (garage.trustgit).
The weekly run is garage-promote.timer (infra/install.d/30-safety.sh). GARAGE_LECHU_ASK overrides the lechu-ask path.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

from . import paths
from . import trust as trust_mod

KIND = "garage.promote"
CARD_MAX = 3300      # lechu-ask keeps 3,500 characters of the command; Telegram shows the first 1,200 (the app all)
ASK_TIMEOUT = 1900   # the broker answers within 30 minutes (unanswered = expired = denied)


def ask_bin():
    return os.environ.get("GARAGE_LECHU_ASK", "/usr/local/bin/lechu-ask")


def candidates():
    """[(rid, record, resource, pin)] for every record that is `reviewed` against today's pin."""
    from . import pins
    try:
        from . import catalog
        res = catalog.load()["resources"]
    except Exception:   # noqa: BLE001 - the card still works from the registry alone
        res = {}
    out = []
    for rid, rec in sorted(trust_mod.load().items()):
        pin = pins.get(rid)
        t, _ = trust_mod.effective(rid, rec, pin)
        if t == "reviewed":
            out.append((rid, rec, res.get(rid) or {}, pin))
    return out


def fingerprint(items):
    s = "\n".join(sorted(f"{rid}@{rec['sha']}" for rid, rec, _, _ in items))
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _name(rid, res):
    return res.get("name") or rid.rsplit("/", 1)[-1]


def _short(text, limit=140):
    """Cut at a word boundary so the owner never reads half a word."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:(") + "…"


def item_line(i, rid, rec, res, pin):
    can = rec.get("can") or {}
    caps = ", ".join(k for k in trust_mod.CAN if can.get(k)) or "no shell/network/files/secrets"
    scans = [s for s in rec.get("scans") or [] if s.get("result") != "skipped"]
    npass = sum(1 for s in scans if s.get("result") == "pass")
    warn = [s["tool"] for s in scans if s.get("result") == "warn"]
    waived = [w["tool"] for w in rec.get("waivers") or []]
    sc = f"{npass}/{len(scans)} scanners pass" + (f", warn: {', '.join(warn)}" if warn else "") + \
        (f", waived: {', '.join(waived)}" if waived else "")
    kind = rec.get("kind") or res.get("use") or res.get("kind") or "item"
    summary = (rec.get("summary") or res.get("note") or "").strip().rstrip(".")
    repo = (pin or {}).get("repo") or ""
    return f"{i}. {_name(rid, res)} ({kind}, {repo}@{rec['sha'][:7]}): {_short(summary)}. Can: {caps}. {sc}."


def build_card(items):
    """-> (items on the card, what, why, card text). Long lists are cut to fit; the rest waits for next week."""
    head = ("Make these reviewed Code Garage items trusted? Trusted = unattended agents (lechu-job, the assistant) may "
            "load them, and they can go into the plugin packs.")
    tail = ("Waived = a scanner flagged a file, and a reviewer read that file and wrote down why it is harmless "
            "(the reasons are in the full reviews). Approve = all of them become trusted. Deny or no answer = they "
            "stay reviewed (interactive use only).")
    who = sorted({str(rec.get("reviewed_by")) for _, rec, _, _ in items})
    head += " Reviewed by " + "; ".join(who[:3]) + ("" if len(who) <= 3 else f" and {len(who) - 3} more") + "."
    lines, kept = [], []
    for rid, rec, res, pin in items:
        ln = item_line(len(kept) + 1, rid, rec, res, pin)
        if len(head) + len(tail) + sum(len(x) + 1 for x in lines) + len(ln) + 60 > CARD_MAX:
            break
        lines.append(ln)
        kept.append((rid, rec, res, pin))
    fp = fingerprint(kept)
    rest = len(items) - len(kept)
    text = "\n".join([head, *lines] + ([f"({rest} more next week.)"] if rest else []) + [tail, f"garage set {fp}"])
    what = f"make {len(kept)} reviewed Code Garage item{'s' if len(kept) != 1 else ''} trusted"
    why = ("Weekly Code Garage promotion: each item passed the scanners and a checklist review "
           "(docs/safety.md). Full reviews: /data/apps/garage/state/reviews/.")
    return kept, what, why, text, fp


def proposal_file(fp):
    return paths.state() / "promote" / f"{fp}.json"


def save_proposal(kept, text, fp):
    f = proposal_file(fp)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"fingerprint": fp, "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                             "items": [{"rid": rid, "sha": rec["sha"]} for rid, rec, _, _ in kept], "card": text},
                            indent=1, ensure_ascii=False), encoding="utf-8")


def ask(what, why, text):
    p = subprocess.run([ask_bin(), KIND, what, "--command", text, "--why", why, "--risk", "medium",
                        "--asker", "garage promote (weekly card)"], capture_output=True, text=True, timeout=ASK_TIMEOUT)
    try:
        return json.loads(p.stdout or "{}")
    except ValueError:
        return {"decision": "error", "note": (p.stderr or p.stdout).strip()[-300:]}


def broker_status(approval_id):
    p = subprocess.run([ask_bin(), "--status", str(int(approval_id))], capture_output=True, text=True, timeout=60)
    try:
        return json.loads(p.stdout or "{}")
    except ValueError:
        return {}


def apply_approval(approval_id, fp=None):
    """Check the approval with the broker, then write `trusted` for the items of that card. -> (written, skipped)."""
    st = broker_status(approval_id)
    if st.get("kind") != KIND or st.get("decision") != "approved":
        raise PermissionError(f"approval #{approval_id} is not an approved {KIND} request "
                              f"(broker says kind {st.get('kind')!r}, decision {st.get('decision')!r})")
    m = re.search(r"garage set ([0-9a-f]{16})\s*$", st.get("command") or "")
    if not m or (fp and m.group(1) != fp):
        raise PermissionError(f"approval #{approval_id} was for a different card (fingerprint mismatch)")
    fp = m.group(1)
    try:
        prop = json.loads(proposal_file(fp).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise LookupError(f"no saved proposal {fp} ({e})") from e
    want = {it["rid"]: it["sha"] for it in prop["items"]}
    if fingerprint([(r, {"sha": s}, None, None) for r, s in want.items()]) != fp:
        raise PermissionError(f"saved proposal {fp} doesn't match its fingerprint")
    from . import pins
    changes, skipped = {}, []
    for rid, sha in want.items():
        rec, pin = trust_mod.record(rid), pins.get(rid)
        t, why = trust_mod.effective(rid, rec, pin)
        if t == "trusted" and rec.get("sha") == sha:
            continue
        if t != "reviewed" or rec.get("sha") != sha:
            skipped.append(f"{rid}: now {t} ({why})")
            continue
        new = dict(rec, trust="trusted", approved_by="owner", approved=dt.date.today().isoformat(),
                   approval=int(approval_id))
        changes[rid] = new
    if changes:
        trust_mod.update(changes, f"owner approval #{approval_id} ({KIND} {fp})", allow_trusted=True)
        from . import trustgit
        trustgit.publish(changes, trustgit.message(sorted(changes), "trusted", f"owner, approval #{approval_id}"))
    return sorted(changes), skipped


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garage promote", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--propose", action="store_true")
    g.add_argument("--record-approval", type=int, metavar="ID")
    g.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the card, send nothing, write nothing")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.record_approval:
        try:
            done, skipped = apply_approval(a.record_approval)
        except (PermissionError, LookupError) as e:
            print(f"garage promote: {e}", file=sys.stderr)
            return 1
        print(json.dumps({"trusted": done, "skipped": skipped}, indent=1) if a.json else
              f"{len(done)} items trusted (approval #{a.record_approval})" + "".join(f"\n  skipped {s}" for s in skipped))
        return 0
    items = candidates()
    if a.list:
        for rid, rec, res, pin in items:
            print(item_line(items.index((rid, rec, res, pin)) + 1, rid, rec, res, pin))
        print(f"{len(items)} reviewed items", file=sys.stderr)
        return 0
    if not items:
        print("Nothing to promote: no reviewed items.")
        return 0
    kept, what, why, text, fp = build_card(items)
    if a.dry_run:
        out = {"what": what, "why": why, "card": text, "fingerprint": fp, "items": [r for r, *_ in kept],
               "sent": False}
        print(json.dumps(out, indent=1, ensure_ascii=False) if a.json else
              f"{what}\n{why}\n---\n{text}\n---\n(dry run: nothing sent, nothing written)")
        return 0
    save_proposal(kept, text, fp)
    res = ask(what, why, text)
    d = res.get("decision")
    trust_mod.log_event({"event": "promote", "fingerprint": fp, "approval": res.get("id"), "decision": d,
                         "items": len(kept)})
    if d != "approved":
        print(f"{what}: {d} (#{res.get('id')}) {res.get('note') or ''}".strip())
        return 0 if d in ("denied", "expired") else 1
    try:
        done, skipped = apply_approval(res["id"], fp)
    except (PermissionError, LookupError) as e:
        print(f"garage promote: approved, but not applied: {e}", file=sys.stderr)
        return 1
    print(f"{len(done)} items trusted (approval #{res['id']})" + "".join(f"\n  skipped {s}" for s in skipped))
    return 0


def health():
    try:
        n = len(candidates())
    except Exception as e:   # noqa: BLE001 - doctor reports, never raises
        return [("WAIT", f"promote: {e}")]
    ok = os.access(ask_bin(), os.X_OK)
    return [("PASS" if ok else "WAIT", f"promote: {n} reviewed items for the next card; "
             + ("lechu-ask present" if ok else f"{ask_bin()} missing (no card can be sent from here)"))]


if __name__ == "__main__":
    sys.exit(main())
