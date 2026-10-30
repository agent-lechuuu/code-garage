"""The generated files. (1) The search index: SQLite FTS5 at $GARAGE_HOME/index/garage.db (the lechu-kb design; rebuilt whole in about a second,
never committed). Rows: one per topic, one per (topic, resource), and chunks of mirrored README / SKILL.md files when
the mirror has the item (garage.mirror.local_path). Columns title, name, tags, note, body weighted 8, 6, 4, 3, 1.

  build(db=None) -> stats dict      build beside the file and swap it in (searches never see half an index)
  connect() -> sqlite3.Connection   a fresh index, read-only; rebuilt first when the catalog/pins/trust changed;
                                    in memory when the index file is stale and not ours to write
(2) `garage build`: INDEX.md (slice -> area -> topic -> resources, readable on GitHub) and dist/catalog.json (the
merged catalog + each resource's pin and trust, for the plugin, the Mac and anyone; catalog.load() reads it when
there is no catalog/ folder). Both are deterministic, so CI can check they are fresh (`garage build --check`).
  render(repo=None) -> {relative path: text}     write_dist(repo=None, check=False) -> [stale or written paths]
"""
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from . import catalog, optional, paths

VERSION = 2
WEIGHTS = "8.0, 6.0, 4.0, 3.0, 1.0"   # bm25 per column: title, name, tags, note, body
CHUNK = 2000
README_MAX = 4096
SKILL_MAX = 16384
EMBED_ON_SEARCH = 32   # new vectors a rebuild inside a search may ask for (garage index embeds them all)
SCHEMA = """
create table meta (k text primary key, v text);
create table docs (id integer primary key, src text, topic text, rid text, slice text);
create index docs_topic on docs(topic);
create table topic_res (topic text, rid text, ord integer, slice text, kind text, use text, license text,
    permissive integer, trust text, tier integer, stars integer);
create index topic_res_topic on topic_res(topic);
create virtual table docs_fts using fts5(title, name, tags, note, body, tokenize='porter unicode61 remove_diacritics 2');
"""

_mem = {}


_tiers = {"fp": None, "map": {}}


def _compute_tiers():
    """{rid: tier} for every runnable resource, in one pass: the registry and the pins are read once (calling
    trust.tier per item re-reads them each time). Falls back to trust.tier, then to quarantine (fail closed)."""
    cat = catalog.load()
    runnable = [rid for rid, r in cat["resources"].items() if catalog.is_runnable(r)]
    t = optional("trust")
    if t is None:
        return {rid: "quarantine" for rid in runnable}
    out = {}
    try:
        if hasattr(t, "effective") and hasattr(t, "load"):
            reg, pins = t.load() or {}, _pins()
            for rid in runnable:
                out[rid] = t.effective(rid, reg.get(rid) or {}, pins.get(rid) or {})[0]
            return out
    except Exception:   # noqa: BLE001 - try the frozen API next
        out = {}
    for rid in runnable:
        try:
            out[rid] = t.tier(rid)
        except Exception:   # noqa: BLE001 - a broken trust module must not open anything up
            out[rid] = "quarantine"
    return out


def tier_of(rid, res):
    """Trust tier: garage.trust when that module exists, else quarantine for runnable items; n/a otherwise.
    Memoised per catalog/pins/trust fingerprint (a changed registry or pin is seen at the next call)."""
    if not catalog.is_runnable(res):
        return "n/a"
    fp = fingerprint()
    if _tiers["fp"] != fp:
        _tiers.update(fp=fp, map=_compute_tiers())
    if rid in _tiers["map"]:
        return _tiers["map"][rid]
    t = optional("trust")
    try:
        return t.tier(rid) if t is not None else "quarantine"
    except Exception:   # noqa: BLE001
        return "quarantine"


def local_path(rid):
    try:
        m = optional("mirror")
        return m.local_path(rid) if m is not None else None
    except Exception:   # noqa: BLE001
        return None


def fingerprint(repo=None):
    repo = Path(repo) if repo else paths.repo()
    files = list(catalog.sources(repo)) + [repo / "lock" / "pins.yaml", repo / "trust" / "registry.yaml"]
    parts = [f"v{VERSION}"]
    for p in files + [paths.mirror(), paths.quarantine()]:
        try:
            st = p.stat()
            parts.append(f"{p}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{p}:-")
    return "|".join(parts)


def _words(s):
    return re.sub(r"[._/\-]+", " ", s or "")


def _split(text):
    text = text.strip()
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if len(cur) + len(para) > CHUNK and cur:
            out.append(cur)
            cur = ""
        cur += para[:CHUNK * 2] + "\n\n"
    if cur.strip():
        out.append(cur)
    return out


def mirror_text(lp):
    """README (first 4 KB) and SKILL.md (up to 16 KB) of a mirrored item, read as plain text, never run."""
    base = Path(lp)
    texts = []
    try:
        for name in ("SKILL.md", "skill.md"):
            f = base / name
            if f.is_file():
                texts.append(f.read_bytes()[:SKILL_MAX].decode("utf-8", "replace"))
                break
        for f in sorted(base.glob("README*")):
            if f.is_file():
                texts.append(f.read_bytes()[:README_MAX].decode("utf-8", "replace"))
                break
    except OSError:
        pass
    return texts


def _fill(c, cat):
    docs, fts, tres = [], [], []
    n = 0

    def add(src, topic, rid, sl, title, name, tags, note, body):
        nonlocal n
        n += 1
        docs.append((n, src, topic, rid, sl))
        fts.append((n, title, name, tags, note, body))

    tiers = {}
    for t in cat["topics"]:
        tid, sl = t["id"], t.get("slice", "")
        practices = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in t.get("practices") or [])
        names = " ".join(r.get("name", "") for r in t.get("resources") or [])
        tags = " ".join([_words(tid), t.get("area", ""), sl] + list(t.get("tags") or []))
        add("topic", tid, None, sl, t.get("title", ""), "", tags, t.get("why", ""), practices + " " + names)
        for k, r in enumerate(t.get("resources") or []):
            rid = r["rid"]
            if rid not in tiers:
                tiers[rid] = tier_of(rid, r)
            gh = catalog.github_repo(r.get("url", ""))
            rtags = " ".join([r.get("kind", ""), r.get("use", ""), str(r.get("license", "")),
                              _words(gh[0]) if gh else "", _words(r.get("path", ""))])
            add("resource", tid, rid, sl, "", r.get("name", ""), rtags, r.get("note", ""), t.get("title", ""))
            stars = r.get("stars") if isinstance(r.get("stars"), int) else 0
            tres.append((tid, rid, k, sl, r.get("kind", ""), r.get("use", ""), str(r.get("license", "")),
                         1 if catalog.is_permissive(r.get("license")) else 0, tiers[rid], int(r.get("tier") or 3),
                         stars))
    chunks = 0
    if optional("mirror") is not None:
        for rid, r in cat["resources"].items():
            lp = local_path(rid)
            if not lp:
                continue
            for text in mirror_text(lp):
                for piece in _split(text):
                    add("mirror", r["topics"][0], rid, r.get("slice", ""), "", r.get("name", ""), "", "", piece)
                    chunks += 1
    c.executemany("insert into docs (id, src, topic, rid, slice) values (?,?,?,?,?)", docs)
    c.executemany("insert into docs_fts (rowid, title, name, tags, note, body) values (?,?,?,?,?,?)", fts)
    c.executemany("insert into topic_res values (?,?,?,?,?,?,?,?,?,?,?)", tres)
    return {"topics": len(cat["topics"]), "resources": len(cat["resources"]), "rows": n, "mirror_chunks": chunks}


def _create(c, cat, fp):
    c.executescript(SCHEMA)
    with c:
        stats = _fill(c, cat)
        c.executemany("insert into meta values (?,?)", [("fingerprint", fp), ("built", time.strftime("%FT%T"))])
    with c:   # (a DML statement opens a transaction: commit it, or close() rolls it back)
        c.execute("insert into docs_fts(docs_fts) values ('optimize')")
    c.execute(f"pragma user_version={VERSION}")
    c.commit()
    return stats


def _vectors(c, old_db, embed_max):
    """Search by meaning (garage.semantic, optional): each row's vector, reused from the old index or embedded."""
    sem = optional("semantic")
    if sem is None:
        return {}
    try:
        return sem.attach(c, old_db, embed_max)
    except Exception as e:   # noqa: BLE001 - the keyword index is complete without vectors
        return {"semantic": f"skipped: {e}"[:200]}


def build(db=None, repo=None, embed_max=None):
    """embed_max: at most this many new vectors (None = all; the rebuild inside connect() keeps it small)."""
    t0 = time.time()
    db = Path(db) if db else paths.index_db()
    db.parent.mkdir(parents=True, exist_ok=True)
    cat = catalog.load(repo)
    fp = fingerprint(repo)
    tmp = db.with_name(db.name + f".new{os.getpid()}")
    tmp.unlink(missing_ok=True)
    c = sqlite3.connect(tmp)
    c.execute("pragma journal_mode=delete")   # readers of another user need no -shm file (WAL would)
    try:
        stats = _create(c, cat, fp)
        stats.update(_vectors(c, db, embed_max))
    finally:
        c.close()
    os.chmod(tmp, 0o644)
    os.replace(tmp, db)
    _mem.clear()
    stats.update(db=str(db), seconds=round(time.time() - t0, 3), kb=db.stat().st_size // 1024)
    return stats


def _fresh(db, fp):
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        row = c.execute("select v from meta where k='fingerprint'").fetchone()
        if row and row[0] == fp:
            return c
        c.close()
    except sqlite3.Error:
        pass
    return None


state = {"stale": False, "note": ""}   # how the last connect() was served (the CLI prints the note)


def _readonly(db):
    """The index file read-only, if it is one of this VERSION (any freshness); else None."""
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        if c.execute("pragma user_version").fetchone()[0] == VERSION and \
                c.execute("select v from meta where k='fingerprint'").fetchone():
            return c
        c.close()
    except sqlite3.Error:
        pass
    return None


def connect(repo=None, db=None):
    """A fresh index if there is one; rebuilt when ours to write; else (the server's index belongs to the garage
    user, rebuilt by garage-sync) the stale file served read-only with state["stale"]; else built in memory."""
    fp = fingerprint(repo)
    db = Path(db) if db else paths.index_db()
    state.update(stale=False, note="")
    c = _fresh(db, fp) if db.exists() else None
    if c:
        return c
    writable = os.access(db if db.exists() else db.parent if db.parent.exists() else db.parent.parent, os.W_OK)
    if writable:
        try:
            build(db, repo, embed_max=EMBED_ON_SEARCH)
            c = _fresh(db, fp)
            if c:
                return c
        except (OSError, sqlite3.Error):
            pass
    if db.exists():
        c = _readonly(db)
        if c:
            state.update(stale=True, note=f"the index {db} is older than the catalog (garage index rebuilds it)")
            return c
    if fp not in _mem:
        _mem.clear()
        m = sqlite3.connect(":memory:", check_same_thread=False)
        _create(m, catalog.load(repo), fp)
        _mem[fp] = m
    state.update(note=f"no usable index at {db}: searched an in-memory index")
    return _mem[fp]


# ---- INDEX.md and dist/catalog.json

def _pins():
    try:
        p = optional("pins")
        return p.all() if p is not None else {}
    except Exception:   # noqa: BLE001
        return {}


def _registry():
    """The trust records (garage.trust.load) so trust works off-server from dist/catalog.json alone."""
    try:
        t = optional("trust")
        return t.load() if t is not None else {}
    except Exception:   # noqa: BLE001
        return {}


def _k(n):
    if not isinstance(n, int):
        return ""
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def _md(s):
    return str(s or "").replace("|", "\\|").replace("[", "(").replace("]", ")").replace("\n", " ")


def render(repo=None):
    cat = catalog.load(repo)
    pins = _pins()
    resources = {}
    for rid, r in cat["resources"].items():
        r = dict(r)
        if catalog.is_runnable(r):
            r["trust"] = tier_of(rid, r)
        pin = pins.get(rid)
        if pin:
            r["pin"] = pin
        resources[rid] = r
    gen = cat.get("generated") or ""
    dist = {"synonyms": cat.get("synonyms") or {}}
    # one topic / resource per line: diffs stay readable, the file stays ~compact
    lines = ['{"version": 1,', f'"generated": {json.dumps(gen)},', '"topics": [']
    tl = [json.dumps(t, ensure_ascii=False, separators=(",", ":")) for t in cat["topics"]]
    lines.append(",\n".join(tl))
    lines.append('],\n"resources": {')
    rl = [f"{json.dumps(k)}:{json.dumps(v, ensure_ascii=False, separators=(',', ':'))}" for k, v in resources.items()]
    lines.append(",\n".join(rl))
    lines.append('},\n"trust_registry": ' + json.dumps(_registry(), ensure_ascii=False, sort_keys=True,
                                                       separators=(",", ":")) + ",")
    lines.append('"synonyms": ' + json.dumps(dist["synonyms"], ensure_ascii=False, separators=(",", ":")) + "}")
    out = {"dist/catalog.json": "\n".join(lines) + "\n"}

    by = {}
    for t in cat["topics"]:
        by.setdefault(t["slice"], {}).setdefault(t.get("area", ""), []).append(t)
    n_run = sum(1 for r in resources.values() if catalog.is_runnable(r))
    legend = ("Each resource: name · licence · stars · tier (t1 = the reference, t2 = solid, t3 = niche) · use · "
              "**trust** for runnable items (quarantine → reviewed → trusted).")
    md = ["# Code Garage index", "",
          "Generated by `garage build` from `catalog/*.yaml`; do not edit by hand. "
          f"{len(cat['topics'])} topics, {len(resources)} resources ({n_run} runnable). "
          "Search with `garage search WORDS`, details with `garage show ID`.", "",
          "This page lists every topic with its first resource; the full lists with licences, stars and trust are "
          "one page per slice:", "",
          "| slice | topics | resources | areas |", "|---|---|---|---|"]
    for sl, areas in by.items():
        ts = [t for a in areas.values() for t in a]
        md.append(f"| [{sl}](dist/index/{sl}.md) | {len(ts)} | {sum(len(t.get('resources') or []) for t in ts)} "
                  f"| {', '.join(areas)} |")
    for sl, areas in by.items():
        md += ["", f"## {sl}", "", f"Full list: [dist/index/{sl}.md](dist/index/{sl}.md)"]
        page = [f"# Code Garage: {sl}", "", f"Generated by `garage build`; back to [INDEX.md](../../INDEX.md). {legend}",
                "", "Areas: " + " · ".join(f"[{a}](#{a}) ({len(ts)})" for a, ts in areas.items())]
        for area, ts in areas.items():
            md += ["", f"### {area}", ""]
            page += ["", f"## {area}"]
            for t in ts:
                rs = t.get("resources") or []
                first = f" — [{_md(rs[0].get('name'))}]({rs[0].get('url')})" if rs else ""
                md.append(f"- **{_md(t.get('title'))}** `{t['id']}`{first} (+{max(len(rs) - 1, 0)})")
                page += ["", f"### {_md(t.get('title'))}", "", f"`{t['id']}`: {_md(t.get('why'))}", ""]
                for r in rs:
                    full = resources.get(r["rid"], r)
                    bits = [str(r.get("license") or "none")]
                    if isinstance(r.get("stars"), int):
                        bits.append(f"{_k(r['stars'])}★")
                    bits.append(f"t{r.get('tier', '?')}")
                    bits.append(str(r.get("use", "")))
                    if full.get("trust"):
                        bits.append(f"**{full['trust']}**")
                    if r.get("archived"):
                        bits.append("archived")
                    page.append(f"- [{_md(r.get('name'))}]({r.get('url')}) · " + " · ".join(bits))
                if t.get("see_also"):
                    page.append("")
                    page.append("See also: " + ", ".join(f"`{x}`" for x in t["see_also"]))
        out[f"dist/index/{sl}.md"] = "\n".join(page) + "\n"
    out["INDEX.md"] = "\n".join(md) + "\n"
    return out


def write_dist(repo=None, check=False):
    """Write the generated files; with check=True write nothing and return the ones that are stale."""
    repo = Path(repo) if repo else paths.repo()
    changed = []
    for rel, text in render(repo).items():
        p = repo / rel
        old = p.read_text(encoding="utf-8") if p.is_file() else None
        if old != text:
            changed.append(rel)
            if not check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
    return changed


def release(c):
    """Close a connection from connect() unless it is the shared in-memory index."""
    if c not in _mem.values():
        c.close()


def health():
    db = paths.index_db()
    if not db.exists():
        return [("WAIT", f"index {db} not built yet (garage index)")]
    c = _fresh(db, fingerprint())
    if not c:
        return [("WAIT", f"index {db} is stale (garage index)")]
    try:
        ok = c.execute("pragma integrity_check").fetchone()[0] == "ok"
        n = c.execute("select count(*) from docs").fetchone()[0]
        has_vec = c.execute("select 1 from sqlite_master where name = 'vec'").fetchone()
        nv = c.execute("select count(*) from vec").fetchone()[0] if has_vec else 0
    finally:
        c.close()
    vec = f", {nv} topic vectors" if nv else ""
    return [("PASS" if ok else "FAIL", f"index {db}: {n} rows{vec}, {db.stat().st_size // 1024} kB")]
