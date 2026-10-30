"""Score `garage search` against tests/eval/needs.yaml (the E1 evaluation set). Stdlib + PyYAML only.

  python3 -m garage.evalset                      score every need, print a table and totals (overall and per slice)
  python3 -m garage.evalset --json               the same as JSON (per need: score, relevance, top 3, reason)
  python3 -m garage.evalset --save FILE          also write the JSON run to FILE
  python3 -m garage.evalset --baseline FILE      print the change per need and per slice against a saved run
  python3 -m garage.evalset --check              only check that every id and rid in needs.yaml exists in the catalog
  python3 -m garage.evalset --via-cli            run `python3 -m garage search --json -n 3` per need instead of the
                                                 in-process call (same code, slower; proves the CLI path)

Scoring (the e2e REPORT's definitions, made mechanical):
  2  the top result is ideal and usable
  1  the top result is acceptable; or an ideal answer is in rank 2-3 (needs digging); or the top result is ideal
     but its best pick is a runnable item still in quarantine, or archived (readable, not addable)
  0  nothing ideal or acceptable in the top 3
A topic id in `ideal`/`acceptable` matches a result's topic id; a rid (normalized URL) matches the result's best
resource. `relevance` is the score before the usability cap, so a ranking change and a review are told apart.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
NEEDS = ROOT / "tests" / "eval" / "needs.yaml"
TOP = 3


def load_needs(path=NEEDS):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    needs = data.get("needs") or []
    for n in needs:
        for k in ("q", "slice", "ideal"):
            if not n.get(k):
                raise SystemExit(f"needs.yaml: need {n!r} lacks {k}")
        n.setdefault("acceptable", [])
        n.setdefault("note", "")
    return needs


def _is_rid(x):
    return "://" in str(x)


def check(needs, cat):
    """Every topic id and rid named in the set exists in the catalog. -> [problems]"""
    from . import catalog
    ids = {t["id"] for t in cat["topics"]}
    rids = set(cat["resources"])
    out = []
    for n in needs:
        for key in ("ideal", "acceptable"):
            for x in n.get(key) or []:
                if _is_rid(x):
                    if catalog.normalize_url(x) not in rids:
                        out.append(f"{n['q']!r}: {key} rid {x} is not in the catalog")
                elif x not in ids:
                    out.append(f"{n['q']!r}: {key} topic {x} is not in the catalog")
    return out


def _run_search(q, via_cli=False):
    if not via_cli:
        from . import search
        return search.search(q, limit=TOP)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "tools"))
    env.setdefault("GARAGE_REPO", str(ROOT))
    p = subprocess.run([sys.executable, "-m", "garage", "search", "--json", "-n", str(TOP)] + q.split(),
                       capture_output=True, text=True, env=env, cwd=str(ROOT), check=False)
    return json.loads(p.stdout or "[]")


def _rid(cat, best):
    from . import catalog
    return catalog.normalize_url(best.get("url", "")) if best else ""


def _hit(cat, res, wanted):
    """Does result `res` (a search row) answer any entry of `wanted` (topic ids and rids)?"""
    rid = _rid(cat, res.get("best") or {})
    for x in wanted:
        if _is_rid(x):
            from . import catalog
            if rid == catalog.normalize_url(x):
                return True
        elif res.get("id") == x:
            return True
    return False


def score_one(need, results, cat):
    """-> {score, relevance, reason, top: [{id, best, trust}]}"""
    from . import catalog
    top = [{"id": r["id"], "best": (r.get("best") or {}).get("name"), "rid": _rid(cat, r.get("best") or {}),
            "trust": (r.get("best") or {}).get("trust"), "kind": (r.get("best") or {}).get("kind"),
            "use": (r.get("best") or {}).get("use")} for r in results[:TOP]]
    if not results:
        return {"score": 0, "relevance": 0, "reason": "no result", "top": top}
    first = results[0]
    if _hit(cat, first, need["ideal"]):
        relevance, reason = 2, "top is ideal"
    elif _hit(cat, first, need["acceptable"]):
        relevance, reason = 1, "top is acceptable"
    elif any(_hit(cat, r, need["ideal"]) for r in results[1:TOP]):
        relevance, reason = 1, "ideal at rank 2-3"
    elif any(_hit(cat, r, need["acceptable"]) for r in results[1:TOP]):
        relevance, reason = 1, "acceptable at rank 2-3"
    else:
        relevance, reason = 0, "miss"
    score = relevance
    best = first.get("best") or {}
    res = cat["resources"].get(_rid(cat, best)) or {}
    if score == 2:
        if catalog.is_runnable(best) and best.get("trust") == "quarantine":
            score, reason = 1, "top is ideal but its best pick is a quarantine " + str(best.get("kind") or "item")
        elif res.get("archived"):
            score, reason = 1, "top is ideal but its best pick is archived"
    return {"score": score, "relevance": relevance, "reason": reason, "top": top}


def run(needs, via_cli=False):
    from . import catalog
    cat = catalog.load()
    out = []
    for n in needs:
        r = score_one(n, _run_search(n["q"], via_cli), cat)
        r.update(q=n["q"], slice=n["slice"])
        out.append(r)
    return out


def totals(rows, key="score"):
    per = OrderedDict()
    for r in rows:
        s = per.setdefault(r["slice"], [0, 0])
        s[0] += r[key]
        s[1] += 2
    return sum(r[key] for r in rows), 2 * len(rows), per


def table(rows, baseline=None):
    base = {b["q"]: b for b in (baseline or [])}
    lines = []
    for r in rows:
        t = r["top"][0] if r["top"] else {}
        delta = ""
        if base.get(r["q"]) is not None:
            d = r["score"] - base[r["q"]]["score"]
            delta = f" ({d:+d})" if d else ""
        lines.append(f"{r['score']}{delta}  {r['slice']:<11} {r['q'][:44]:<44} -> {t.get('id', '-')} / "
                     f"{t.get('best', '-')} [{t.get('trust', '-')}]  {r['reason']}")
    tot, mx, per = totals(rows)
    rel, _, per_rel = totals(rows, "relevance")
    lines.append("")
    lines.append(f"TOTAL {tot}/{mx} (relevance before the trust cap: {rel}/{mx})")
    for sl, (s, m) in per.items():
        extra = ""
        if baseline:
            bs = sum(b["score"] for b in baseline if b["slice"] == sl)
            extra = f"  (was {bs})"
        lines.append(f"  {sl:<11} {s}/{m}  relevance {per_rel[sl][0]}/{m}{extra}")
    if baseline:
        bt = sum(b["score"] for b in baseline)
        lines.append(f"  baseline {bt}/{2 * len(baseline)} -> {tot}/{mx}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garage evalset", description=__doc__.splitlines()[0])
    ap.add_argument("--needs", default=str(NEEDS))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save")
    ap.add_argument("--baseline")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--via-cli", action="store_true")
    a = ap.parse_args(argv)
    needs = load_needs(a.needs)
    from . import catalog
    problems = check(needs, catalog.load())
    if a.check or problems:
        for p in problems:
            print("ERROR", p)
        print(f"{len(needs)} needs, {len(problems)} problems")
        if problems or a.check:
            return 1 if problems else 0
    rows = run(needs, via_cli=a.via_cli)
    if a.save:
        Path(a.save).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    baseline = json.loads(Path(a.baseline).read_text(encoding="utf-8")) if a.baseline else None
    if a.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
    else:
        print(table(rows, baseline))
    return 0


if __name__ == "__main__":
    sys.exit(main())
