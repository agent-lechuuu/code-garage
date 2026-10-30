"""Find things in the garage. One module for the CLI, the stdio MCP and the HTTP MCP.

  search(q, kind=None, use=None, slice=None, trust=None, license=None, limit=5)
      -> [{id, title, why, score, best: {name, url, kind, use, license, trust, install, local_path}}]
  show(id_or_url) -> dict    a topic (with its resources and the recipe for each) or one resource; {} if unknown
  resolve(ref) -> (topic or None, [resources])   topic id, URL/rid, owner/repo[/path], or a resource name
  grep(ref, pattern) -> {rid, root, matches: [{file, line, text}], truncated}   ripgrep inside one mirrored snapshot

Query: words (letters, digits, _ and '), -word = NOT, the last word also as a prefix; little words dropped; each
word expanded with catalog/synonyms.yaml. All words first (AND), then any word (OR) to fill up to `limit`. Results
are folded per topic: a topic's score is its best row; `best` is its best resource that passes the filters
(a matching row first, then tier, then stars). license: an SPDX id, or "permissive". Answers stay under ~3 KB.
When garage.semantic answers (the embedding service on the server), the 30 best keyword topics and the topics nearest
in meaning are fused by reciprocal rank; when it doesn't, nothing changes.
"""
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import catalog, index, optional

STOP = set("a an and are as at be but by for from has have i in is it its me my of on or our so that the this to "
           "was we what when where which who why will with you your can could do did does how about into than then "
           "there these they those just also any all need want use using make build some like get".split())
WHY_MAX = 160
NOTE_MAX = 220
ANSWER_MAX = 3072   # bytes of JSON per answer: agents' context (Claude Code warns above 10k tokens per MCP result)


def terms_of(q, synonyms=None):
    """-> (positive terms, negative terms). Terms are words; a multi-word synonyms.yaml key found in the query
    ("ring buffer") becomes one phrase term. C++ / C# are read as cpp / csharp first."""
    pos, neg = [], []
    q = re.sub(r"(?i)(?<!\w)c\+\+", "cpp", str(q))
    q = re.sub(r"(?i)(?<!\w)c#", "csharp", q)
    for raw in q.split():
        no = raw.startswith("-") and len(raw) > 1
        for w in re.sub(r"[^\w']+", " ", raw[1:] if no else raw).split():
            w = w.strip("'_").lower()
            if w:
                (neg if no else pos).append(w)
    pos = [w for w in pos if w not in STOP] or pos
    phrases = sorted((k for k in (synonyms or {}) if re.search(r"[\s-]", k)),
                     key=lambda k: -len(re.split(r"[\s-]+", k)))
    for ph in phrases:
        words = re.split(r"[\s-]+", ph)
        for i in range(len(pos) - len(words) + 1):
            if pos[i:i + len(words)] == words:
                pos[i:i + len(words)] = [ph]
                break
    return pos[:20], neg[:10]


# ---- intent: a language or a kind named in the query is a preference, not a required word ---------------------------

LANG_WORDS = {"cpp": "cpp", "c": "c", "rust": "rust", "go": "go", "golang": "go", "python": "python", "py": "python",
              "java": "java", "kotlin": "kotlin", "javascript": "js", "js": "js", "typescript": "js", "ts": "js",
              "node": "js", "nodejs": "js", "solidity": "solidity", "vyper": "vyper", "csharp": "csharp",
              "dotnet": "csharp", "swift": "swift", "ruby": "ruby", "php": "php", "zig": "zig", "elixir": "elixir",
              "haskell": "haskell", "scala": "scala", "lua": "lua", "dart": "dart", "cairo": "cairo"}
LANG_RX = {   # how a resource or topic says it is of that language (name, note, url, topic id/title)
    "cpp": re.compile(r"c\+\+|\bcpp\b|\bhpp\b|cplusplus", re.I),
    "c": re.compile(r"(?<![\w+#.-])C(?![\w+#-])|\bsystems\.c\."),
    "rust": re.compile(r"\brust\b|\bcrates?\b|\bcargo\b", re.I),
    "go": re.compile(r"\bgolang\b|(?<![\w.-])Go(?![\w-])|\.go\.|\bgo\.dev\b"),
    "python": re.compile(r"\bpython\b|\bpypi\b|\bdjango\b|\bfastapi\b", re.I),
    "java": re.compile(r"\bjava\b|\bjvm\b", re.I),
    "kotlin": re.compile(r"\bkotlin\b", re.I),
    "js": re.compile(r"\bjavascript\b|\btypescript\b|\bnode(?:\.?js)?\b|\bnpm\b|\bjs\b|\breact\b", re.I),
    "solidity": re.compile(r"\bsolidity\b|\bfoundry\b|\bforge\b|\bevm\b", re.I),
    "vyper": re.compile(r"\bvyper\b", re.I),
    "csharp": re.compile(r"\bc#|\bcsharp\b|\.net\b|\bdotnet\b", re.I),
    "swift": re.compile(r"\bswift\b", re.I), "ruby": re.compile(r"\bruby\b|\brails\b", re.I),
    "php": re.compile(r"\bphp\b|\blaravel\b", re.I), "zig": re.compile(r"\bzig\b", re.I),
    "elixir": re.compile(r"\belixir\b", re.I), "haskell": re.compile(r"\bhaskell\b", re.I),
    "scala": re.compile(r"\bscala\b", re.I), "lua": re.compile(r"\blua\b", re.I),
    "dart": re.compile(r"\bdart\b|\bflutter\b", re.I), "cairo": re.compile(r"\bcairo\b|\bstarknet\b", re.I),
}
KIND_WORDS = {"mcp": "mcp", "skill": "skill", "skills": "skill", "plugin": "plugin", "plugins": "plugin",
              "template": "template", "templates": "template", "starter": "template", "boilerplate": "template",
              "scaffold": "template", "checklist": "checklist", "checklists": "checklist",
              "cheatsheet": "cheatsheet", "cheat sheet": "cheatsheet", "cheat sheets": "cheatsheet"}
SOFT = {"fast", "faster", "fastest", "low", "latency", "lightweight", "simple", "minimal", "modern", "best", "good",
        "efficient", "performant", "high", "quick", "small", "tiny", "popular", "library", "libraries", "lib",
        "implementation", "example", "examples"}
TEST_WORDS = {"test", "tests", "testing", "fuzz", "fuzzing", "e2e", "tdd", "spec", "invariant", "invariants", "audit"}


def intent(pos):
    """-> (core terms that must all match, {languages}, {kinds}). Language and kind words, adjectives like
    'low-latency', and 'server' after 'mcp' only rank: an item need not repeat them to be the answer."""
    langs = {LANG_WORDS[w] for w in pos if w in LANG_WORDS}
    kinds = {KIND_WORDS[w] for w in pos if w in KIND_WORDS}
    soft = set(SOFT) | ({"server", "servers"} if "mcp" in kinds else set())
    core = [w for w in pos if w not in LANG_WORDS and w not in KIND_WORDS and w not in soft]
    return core or pos, langs, kinds


def _langs_in(text):
    return {k for k, rx in LANG_RX.items() if rx.search(text or "")}


def _kind_ok(res, k):
    name = f"{res.get('name', '')} {res.get('url', '')}".lower()
    if k == "cheatsheet":
        return "cheat sheet" in name or "cheatsheet" in name or "cheat-sheet" in name
    if k == "checklist":
        return res.get("kind") == "checklist" or "checklist" in name
    return k in (res.get("kind"), res.get("use"))


class Prefs:
    """Row factors from the query's intent: of the asked language x1.5 (of only another language x0.6), of the asked
    kind x1.6, a test suite x0.75 when the query isn't about tests. Cached per resource and topic."""

    def __init__(self, cat, pos, langs, kinds):
        self.cat, self.langs, self.kinds = cat, langs, kinds
        self.tests = bool(TEST_WORDS & set(pos))
        self.by_id = catalog.topics_by_id(cat)
        self.memo = {}

    def __bool__(self):
        return bool(self.langs or self.kinds or not self.tests)

    def lang(self, text):
        if not self.langs:
            return 1.0
        found = _langs_in(text)
        if found & self.langs:
            return 1.5
        return 0.6 if found else 1.0

    def factor(self, tid, rid):
        key = (tid, rid)
        if key in self.memo:
            return self.memo[key]
        f = 1.0
        if rid:
            r = self.cat["resources"].get(rid) or {}
            f *= self.lang(f"{r.get('name', '')} {r.get('note', '')} {r.get('url', '')}")
            if self.kinds and any(_kind_ok(r, k) for k in self.kinds):
                f *= 1.6
            if not self.tests and re.search(r"\btests?\b|test-?suite", str(r.get("name", "")), re.I):
                f *= 0.75
        else:
            t = self.by_id.get(tid) or {}
            f *= self.lang(f"{tid.replace('.', ' . ').replace('-', ' ')} {t.get('title', '')}") ** 0.6
            if self.kinds and any(k in tid.split(".")[1:] or k + "s" in tid.split(".")[1:] for k in self.kinds):
                f *= 1.2
        self.memo[key] = f
        return f


def _quote(w):
    return '"' + w.replace('"', "") + '"'


def match_expr(pos, neg, op, synonyms, extra=()):
    """FTS5 expression: the terms (each with its synonyms) joined by op. `extra` terms only score: they are OR-ed with
    the first term, so they never decide whether a row matches."""
    groups = []
    for k, w in enumerate(pos):
        alts = [_quote(w)]   # stemmed by the porter tokenizer
        if k == len(pos) - 1 and len(w) >= 3 and not re.search(r"[\s-]", w):
            alts.append(_quote(w) + "*")   # the last word may be half typed (a prefix is not stemmed)
        for s in synonyms.get(w, []) or []:
            alts.append(_quote(str(s).lower()))
        groups.append("(" + " OR ".join(dict.fromkeys(alts)) + ")" if len(alts) > 1 else alts[0])
    expr = f" {op} ".join(groups)
    if extra and groups:
        expr += " AND (" + " OR ".join([groups[0]] + [_quote(w) for w in extra]) + ")"
    for w in neg:
        expr += f" NOT {_quote(w)}"
    return expr


def _filters(kind, use, slice, trust, license):
    where, args = [], []
    for col, v in (("kind", kind), ("use", use), ("slice", slice), ("trust", trust)):
        if v:
            vals = [x.strip() for x in str(v).split(",") if x.strip()]
            where.append(f"{{p}}{col} in ({','.join('?' * len(vals))})")
            args += vals
    if license:
        if str(license).lower() == "permissive":
            where.append("{p}permissive = 1")
        else:
            where.append("lower({p}license) like ?")
            args.append(str(license).lower() + "%")
    return where, args


def _and(where, prefix):
    return " and ".join(w.replace("{p}", prefix) for w in where)


def install_line(res):
    """How to use the item, in one line: the curated `install` field, else derived from use/kind/url."""
    if res.get("install"):
        return res["install"]
    u, use = res.get("url", ""), res.get("use")
    m = re.match(r"https://www\.npmjs\.com/package/((?:@[^/]+/)?[^/?#]+)", u)
    if m:
        return f"npm install {m.group(1)}"
    m = re.match(r"https://pypi\.org/project/([^/?#]+)", u)
    if m:
        return f"pip install {m.group(1)}"
    m = re.match(r"https://crates\.io/crates/([^/?#]+)", u)
    if m:
        return f"cargo add {m.group(1)}"
    m = re.match(r"https://pkg\.go\.dev/([^?#]+)", u)
    if m and use == "install":
        return f"go get {m.group(1)}"
    ref = res.get("rid") or catalog.normalize_url(u)
    if use == "skill" or res.get("kind") == "skill":
        return f"garage skill add {ref}"
    if use in ("vendor", "template", "mcp", "plugin") or catalog.is_runnable(res):
        return f"garage add {ref}"
    if use == "install":
        return _install_from_note(res) or _install_from_name(res) or f"install as its README says: {u}"
    return None


INSTALL_CMD = re.compile(
    r"(?<![\w-])(npm (?:i|install)|pnpm add|yarn add|bun add|pip3? install|uv add|uv tool install|pipx install|"
    r"cargo (?:add|install)|go (?:get|install)|brew install|gem install|forge install|claude plugin install|"
    r"composer require|dotnet add package|conda install|vcpkg install|opam install|cabal install)"
    r"((?:\s+-{1,2}[\w-]+(?:=\S+)?)*)\s+([@\w][\w@./:+~-]*\w)")


def _norm(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _install_from_note(res):
    """An install command the curated note itself spells out, kept only when its package is this item (its repo,
    path or name), never another package the note mentions in passing."""
    m = re.match(r"https?://[^/]+/(.*)", res.get("url", ""))
    skip = ("tree", "blob", "HEAD", "main", "master")
    parts = [p for p in (m.group(1) if m else "").split("/") if p and p not in skip]
    names = {_norm(p) for p in parts[1:2] + parts[-1:]} | {_norm(res.get("name")),
                                                          _norm(re.split(r"[\s(]", res.get("name") or "")[0])}
    names = {n for n in names if len(n) >= 2}
    for c in INSTALL_CMD.finditer(str(res.get("note") or "")):
        pkg = c.group(3)
        if re.search(r"[<>]|owner/repo|your-|example", pkg):
            continue
        last = _norm((pkg.split("/")[-1] if pkg.startswith("@") else pkg.split("/")[-1]).split("@")[0])
        if last in names or (len(last) >= 4 and any(n.startswith(last) for n in names)):
            return f"{c.group(1)}{c.group(2) or ''} {pkg}"
    return None


def _install_from_name(res):
    """A name that is itself an npm package (@scope/name, nothing else)."""
    m = re.fullmatch(r"(@[a-z0-9][\w.-]*/[a-z0-9][\w.-]*)", str(res.get("name") or "").strip())
    return f"npm install {m.group(1)}" if m else None


def trust_of(res):
    return index.tier_of(res["rid"], res)


def _brief(res):
    return {"name": res.get("name"), "url": res.get("url"), "kind": res.get("kind"), "use": res.get("use"),
            "license": res.get("license"), "trust": trust_of(res), "install": install_line(res),
            "local_path": index.local_path(res["rid"])}


def _short(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


TIER_FACTOR = {1: 1.0, 2: 0.85, 3: 0.7}


def _rank(rows, prefs=None):
    """rows [(topic, rid, bm25)] -> ({topic: relevance}, {(topic, rid): relevance}). A topic's relevance is its best
    row plus a little of its next two (a topic whose title and resources both match beats one lucky resource). prefs
    (the query's language/kind intent) scales each row first."""
    per, hits = {}, {}
    for tid, rid, s in rows:
        rel = -s * (prefs.factor(tid, rid) if prefs else 1.0)
        per.setdefault(tid, []).append(rel)
        if rid and rel > hits.get((tid, rid), 0.0):
            hits[(tid, rid)] = rel
    score = {}
    for tid, rels in per.items():
        rels.sort(reverse=True)
        score[tid] = rels[0] + 0.3 * sum(rels[1:3])
    return score, hits


def _pick(cands, tid, hits):
    """The best resource of a topic: matching rows first (relevance x tier x a little for stars), then tier, stars."""
    def key(x):
        rid, tier, stars = x
        rel = hits.get((tid, rid), 0.0)
        boost = TIER_FACTOR.get(tier, 0.7) * (1 + 0.04 * math.log10((stars or 0) + 1))
        return (rel * boost, -(tier or 3), stars or 0)
    return max(cands, key=key)[0]


def _row_filter(slice, fwhere, fargs):
    """SQL (on docs d) and args: the row's slice, and only topics with a resource that passes the filters; a failing
    resource row must not pick `best`."""
    sql, args = "", []
    if slice:
        vals = [x.strip() for x in str(slice).split(",") if x.strip()]
        sql += f" and d.slice in ({','.join('?' * len(vals))})"
        args += vals
    if fwhere:
        sql += " and d.topic in (select topic from topic_res where " + _and(fwhere, "") + ")"
        sql += (" and (d.rid is null or exists (select 1 from topic_res r where r.topic = d.topic and "
                "r.rid = d.rid and " + _and(fwhere, "r.") + "))")
        args += fargs + fargs
    return sql, args


def _keyword(c, pos, neg, core, soft, synonyms, prefs, rfilter, depth):
    """FTS5: all core words (AND), then any word (OR) to fill up to `depth` topics. -> (order, scores, hits)."""
    order, hits, scores = [], {}, {}
    for mode in ("AND", "OR") if len(pos) > 1 else ("AND",):
        terms = core if mode == "AND" else pos
        sql = ("select d.topic, d.rid, bm25(docs_fts, " + index.WEIGHTS + ") as s from docs_fts "
               "join docs d on d.id = docs_fts.rowid where docs_fts match ?")
        args = [match_expr(terms, neg, mode, synonyms, soft if mode == "AND" else ())]
        sql += rfilter[0] + " order by s limit 800"
        score, h = _rank(c.execute(sql, args + rfilter[1]).fetchall(), prefs if prefs else None)
        for tid in sorted(score, key=lambda t: -score[t]):
            if tid not in scores and len(order) < depth:
                order.append(tid)
                scores[tid] = score[tid]
        for k, v in h.items():
            hits.setdefault(k, v)
        if len(order) >= depth:
            break
    return order, scores, hits


# ---- search by meaning (garage.semantic): only when its service answers, else the keyword ranking alone -----------
# Measured on tests/eval/needs.yaml and tests/t5/paraphrases.yaml (tests/t5): the vectors re-rank the keyword
# candidates; a heavier vector weight wins more plain-word queries but costs owner needs (tests/t1 NEEDS).

RRF_K = 20          # reciprocal rank fusion: 1 / (RRF_K + rank)
FTS_DEPTH = 30      # keyword topics taken into the fusion
VEC_WEIGHT = 0.5    # the vector ranking's weight; the keyword ranking's is 1
VEC_MIN = 0.55      # cosine a topic no keyword found needs to be offered (MiniLM: off-topic queries stay under 0.4)


def _vector(c, q, neg, prefs, rfilter, k=100):
    """-> {topic: similarity} of the topics nearest the query that pass the filters, or {} (off, no vectors, no
    answer in time). The query's language/kind intent nudges each, as in the keyword ranking."""
    sem = optional("semantic")
    if sem is None:
        return {}
    try:
        near = dict(sem.vector_hits(c, q, k))
    except Exception:   # noqa: BLE001 - search by meaning is an extra: never fail a search over it
        near = {}
    if not near:
        return {}
    ids = list(near)
    rows = c.execute(f"select d.id, d.topic from docs d where d.id in ({','.join('?' * len(ids))})" + rfilter[0],
                     ids + rfilter[1]).fetchall()
    if neg and rows:   # -word: a topic whose text has it is out, as in the keyword search
        bad = {r[0] for r in c.execute(
            f"select rowid from docs_fts where docs_fts match ? and rowid in ({','.join('?' * len(rows))})",
            [" OR ".join(_quote(w) for w in neg)] + [r[0] for r in rows])}
        rows = [r for r in rows if r[0] not in bad]
    out = {}
    for i, tid in rows:
        f = prefs.factor(tid, None) if prefs else 1.0
        out[tid] = max(out.get(tid, -1.0), near[i] * f ** 0.15)   # cosines sit close together: a gentle nudge
    return out


def _fuse(order, vscore, limit):
    """Reciprocal rank fusion of the keyword order and the vector ranking -> (topics, fused scores)."""
    fused = {}
    for r, tid in enumerate(order):
        fused[tid] = 1.0 / (RRF_K + r + 1)
    for r, tid in enumerate(sorted(vscore, key=lambda t: -vscore[t])):
        if tid in fused or vscore[tid] >= VEC_MIN:
            fused[tid] = fused.get(tid, 0.0) + VEC_WEIGHT / (RRF_K + r + 1)
    top = sorted(fused, key=lambda t: -fused[t])[:limit]
    return top, {t: round(fused[t] * 100, 2) for t in top}


def search(q, kind=None, use=None, slice=None, trust=None, license=None, limit=5):
    limit = max(1, min(int(limit or 5), 50))
    cat = catalog.load()
    synonyms = cat.get("synonyms") or {}
    pos, neg = terms_of(q, synonyms)
    if not pos:
        return []
    core, langs, kinds = intent(pos)
    soft = [w for w in pos if w not in core]
    prefs = Prefs(cat, pos, langs, kinds)
    fwhere, fargs = _filters(kind, use, None, trust, license)
    rfilter = _row_filter(slice, fwhere, fargs)
    c = index.connect()
    try:
        vscore = _vector(c, q, neg, prefs, rfilter)
        order, scores, hits = _keyword(c, pos, neg, core, soft, synonyms, prefs, rfilter,
                                       max(limit, FTS_DEPTH) if vscore else limit)
        if vscore:
            order, scores = _fuse(order, vscore, limit)
        out = []
        by_id = catalog.topics_by_id(cat)
        for tid in order:
            sql = "select rid, tier, stars from topic_res where topic = ?"
            args = [tid]
            if fwhere:
                sql += " and " + _and(fwhere, "")
                args += fargs
            cands = c.execute(sql + " order by ord", args).fetchall()
            res = cat["resources"].get(_pick(cands, tid, hits)) if cands else None
            if not res:
                continue
            t = by_id.get(tid) or {}
            out.append({"id": tid, "title": t.get("title"), "why": _short(t.get("why"), WHY_MAX),
                        "score": round(scores[tid], 2), "best": _brief(res)})
        return out
    finally:
        index.release(c)


def resolve(ref):
    """-> (topic or None, [resource dicts])."""
    cat = catalog.load()
    ref = str(ref).strip()
    t = catalog.topics_by_id(cat).get(ref)
    if t:
        return t, [cat["resources"][r["rid"]] for r in t.get("resources") or [] if r["rid"] in cat["resources"]]
    res = cat["resources"]
    if "://" in ref:
        rid = catalog.normalize_url(ref)
        return (None, [res[rid]]) if rid in res else (None, [])
    low = ref.lower().strip("/")
    if re.fullmatch(r"[\w.-]+/[\w.-]+(/.+)?", low):
        rid = "https://github.com/" + low
        exact = [r for k, r in res.items() if k.lower() == rid]
        if exact:
            return None, exact
        sub = [r for k, r in res.items() if (catalog.github_repo(r["url"]) or ("", ""))[0].lower() == low]
        if sub:
            return None, sorted(sub, key=lambda r: (len(r["rid"]), r["rid"]))
    by_name = [r for r in res.values() if str(r.get("name", "")).lower() == low]
    return None, by_name


def _pin(rid):
    try:
        p = optional("pins")
        return p.get(rid) if p is not None else None
    except Exception:   # noqa: BLE001
        return None


def recipe(res):
    """Everything an agent needs to use one resource, in a small dict."""
    pin = _pin(res["rid"]) or res.get("pin")
    out = {"rid": res["rid"], "name": res.get("name"), "url": res.get("url"), "kind": res.get("kind"),
           "use": res.get("use"), "license": res.get("license"), "tier": res.get("tier"),
           "stars": res.get("stars"), "trust": trust_of(res), "runnable": catalog.is_runnable(res),
           "install": install_line(res), "local_path": index.local_path(res["rid"]),
           "note": _short(res.get("note"), NOTE_MAX)}
    if res.get("path"):
        out["path"] = res["path"]
    if res.get("archived"):
        out["archived"] = True
    if pin:
        out["pin"] = {k: pin.get(k) for k in ("sha", "pinned", "license_at_pin", "policy", "size_kb") if pin.get(k)}
    return {k: v for k, v in out.items() if v not in (None, "")}


def show(id_or_url):
    t, rs = resolve(id_or_url)
    if t:
        out = {"id": t["id"], "title": t.get("title"), "slice": t.get("slice"), "area": t.get("area"),
               "why": t.get("why"),
               "practices": [_short(p.get("text") if isinstance(p, dict) else p, 200) for p in t.get("practices") or []],
               "resources": [], "see_also": t.get("see_also") or []}
        for r in rs:
            rec = recipe(r)
            for k in ("stars", "rid", "runnable"):   # rid ~ url; runnable = trust is not n/a
                rec.pop(k, None)
            out["resources"].append(rec)
        for n in (160, 100, 60, 0):   # stay under ~3 KB: shorten the notes, then drop them
            if len(json.dumps(out, ensure_ascii=False).encode()) <= ANSWER_MAX:
                break
            for rec in out["resources"]:
                if n and rec.get("note"):
                    rec["note"] = _short(rec["note"], n)
                else:
                    rec.pop("note", None)
        return out
    if not rs:
        return {}
    r = rs[0]
    out = recipe(r)
    out["topics"] = r.get("topics", [])
    if len(rs) > 1:
        out["also"] = [x["rid"] for x in rs[1:6]]
    return out


GREP_FILE_MAX = 2_000_000


def _grep_python(rx, root, limit):
    out = []
    for dirpath, dirs, files in os.walk(root):   # os.walk does not follow symlinked folders
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            f = Path(dirpath) / name
            try:
                if f.is_symlink() or f.stat().st_size > GREP_FILE_MAX:
                    continue
                data = f.read_bytes()
            except OSError:
                continue
            if b"\0" in data[:8192]:
                continue
            for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if rx.search(line):
                    out.append({"file": str(f.relative_to(root)), "line": n, "text": line[:300]})
                    if len(out) >= limit:
                        return out, True
    return out, False


def grep(ref, pattern, ignore_case=False, limit=100):
    """Search one mirrored snapshot (read-only; the files are data, nothing in them is run)."""
    t, rs = resolve(ref)
    if not rs:
        return {"ok": False, "reason": f"nothing in the garage matches {ref!r}"}
    hit = next(((r, lp) for r in rs if (lp := index.local_path(r["rid"]))), None)
    if not hit:
        return {"ok": False, "rid": rs[0]["rid"],
                "reason": "not mirrored here (yet): only snapshots on this machine can be grepped"}
    res, root = hit[0], Path(hit[1])
    limit = max(1, min(int(limit), 1000))
    matches, truncated = [], False
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "--no-config", "--no-ignore", "--hidden", "--no-follow", "-n", "--no-heading", "--color", "never",
               "--max-columns", "300", "--max-filesize", "2M", "--sort", "path", "-g", "!.git"] + (["-i"] if ignore_case else [])
        cmd += ["-e", pattern, "--", "."]
        try:
            with subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                  errors="replace", env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")}) as p:
                for line in p.stdout:
                    f, _, rest = line.rstrip("\n").partition(":")
                    n, _, text = rest.partition(":")
                    matches.append({"file": f.removeprefix("./"), "line": int(n) if n.isdigit() else 0, "text": text})
                    if len(matches) >= limit:
                        truncated = True
                        break
                p.kill()
        except (OSError, subprocess.SubprocessError):
            matches, rg = [], None
    if not rg:
        try:
            rx = re.compile(pattern, re.I if ignore_case else 0)
        except re.error as e:
            return {"ok": False, "reason": f"bad pattern: {e}"}
        matches, truncated = _grep_python(rx, root, limit)
    return {"ok": True, "rid": res["rid"], "root": str(root), "pattern": pattern, "matches": matches,
            "truncated": truncated}


def health():
    try:
        n = len(search("test", limit=1))
        out = [("PASS" if n else "FAIL", "search answers ('test' → %d)" % n)]
    except Exception as e:   # noqa: BLE001
        return [("FAIL", f"search: {e}")]
    sem = optional("semantic")
    try:
        return out + (sem.health() if sem is not None else [])
    except Exception as e:   # noqa: BLE001 - an extra: never a FAIL of search itself
        return out + [("WAIT", f"search by meaning: {e}")]
