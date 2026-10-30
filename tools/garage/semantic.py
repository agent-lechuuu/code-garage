"""Search by meaning (optional): a sentence embedding per topic, fused with the FTS5 keyword ranking (search.py).

Off unless something can embed a query; then the garage answers as before plus what the words alone miss
("lock down a background service" -> systemd hardening). Measured choices (tests/t5, infra/checks/t5.sh):
  - one vector per topic (title, why, practices, resource names): beat adding resources and README chunks
  - all-MiniLM-L6-v2 (Apache-2.0, ONNX, CPU): beat bge-small-en-v1.5 and is 2.7x faster to embed
  - the vectors live in the index (table `vec`: int8, 384 bytes a topic) and are swapped in with it; the cosine over
    ~1k topics is plain Python (~12 ms), so the CLI, the MCP and the tailnet container import nothing heavy
  - the model runs once per server, in garage-embed.service (unix socket $GARAGE_HOME/run/embed.sock, socket
    activated, exits when idle). No service, or slower than TIMEOUT: keyword search alone, silently.

  GARAGE_SEMANTIC   service (default: ask the service) | local (load the model in this process: the Mac with
                    `pip install 'code-garage[semantic]'` and `python -m garage.semantic fetch`) | 0 (off)
  python -m garage.semantic fetch | verify | serve [--idle S] | status
"""
import array
import base64
import hashlib
import json
import math
import operator
import os
import socket
import sqlite3
import sys
import time
from pathlib import Path

from . import paths

MODEL = "all-MiniLM-L6-v2"
MODELS = {   # exact revisions; every file is checked by sha256 before it is used
    "all-MiniLM-L6-v2": {
        "repo": "Qdrant/all-MiniLM-L6-v2-onnx", "rev": "d13954661f83248295ba75c1ed411eef3b7b936e",
        "license": "Apache-2.0", "onnx": "model.onnx", "pool": "mean", "dim": 384, "query_prefix": "",
        "files": {"model.onnx": "bbd7b466f6d58e646fdc2bd5fd67b2f5e93c0b687011bd4548c420f7bd46f0c5",
                  "tokenizer.json": "851ca67100d372ca3ae031a6abd168f53489eebfd7d89523f35c5c9b4d372c3c",
                  "config.json": "1b4d8e2a3988377ed8b519a31d8d31025a25f1c5f8606998e8014111438efcd7"}},
    "bge-small-en-v1.5": {   # measured against; kept for comparison runs (GARAGE_EMBED_MODEL)
        "repo": "Qdrant/bge-small-en-v1.5-onnx-Q", "rev": "aa8f8b060edb00e03bfdd08813a2949946c8ba55",
        "license": "MIT", "onnx": "model_optimized.onnx", "pool": "cls", "dim": 384,
        "query_prefix": "Represent this sentence for searching relevant passages: ",
        "files": {"model_optimized.onnx": "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431",
                  "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
                  "config.json": "13582bcf2effc85b7bf3d3f5532e686bc1c9ce86bb009d10f0ec33cbe92299dd"}},
}
SRCS = ("topic",)    # index rows that get a vector
MAX_TOKENS = 256
TIMEOUT = 0.3        # seconds for one query to the service; past it, keyword search alone
MAX_REQUEST = 1 << 20
MAX_TEXTS = 64


def model_name():
    return os.environ.get("GARAGE_EMBED_MODEL") or MODEL


def models_dir():
    env = os.environ.get("GARAGE_MODELS")
    if env:
        return Path(env)
    return Path("/opt/garage/models") if Path("/opt/garage/models").is_dir() else paths.home() / "models"


def model_dir(name=None):
    name = name or model_name()
    return models_dir() / name / MODELS[name]["rev"]


def socket_path():
    return Path(os.environ.get("GARAGE_EMBED_SOCKET") or paths.home() / "run" / "embed.sock")


def mode():
    v = os.environ.get("GARAGE_SEMANTIC", "service").strip().lower()
    return {"0": "off", "no": "off", "false": "off", "off": "off", "local": "local"}.get(v, "service")


# ---- the model files: pinned revision, sha256 checked ---------------------------------------------------------------

def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def verify(d=None, name=None):
    """-> [problems] with the model files in d (empty: all there, all matching their sha256)."""
    name = name or model_name()
    d = Path(d) if d else model_dir(name)
    bad = []
    for f, sha in MODELS[name]["files"].items():
        p = d / f
        if not p.is_file():
            bad.append(f"missing {p}")
        elif _sha256(p) != sha:
            bad.append(f"sha256 mismatch {p}")
    return bad


def fetch(dest=None, name=None):
    """Download the pinned model files (Hugging Face, exact revision) into dest. Each file is checked by sha256
    before it is moved into place. -> the folder."""
    import urllib.request
    name = name or model_name()
    m = MODELS[name]
    dest = Path(dest) if dest else model_dir(name)
    dest.mkdir(parents=True, exist_ok=True)
    for f, sha in m["files"].items():
        p = dest / f
        if p.is_file() and _sha256(p) == sha:
            continue
        url = f"https://huggingface.co/{m['repo']}/resolve/{m['rev']}/{f}"
        tmp = p.with_name(p.name + ".part")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as out:
            while b := r.read(1 << 20):
                out.write(b)
        got = _sha256(tmp)
        if got != sha:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"{url}: sha256 {got}, expected {sha}")
        os.chmod(tmp, 0o644)
        os.replace(tmp, p)
    return dest


class Embedder:
    """The model on the CPU (numpy, onnxruntime, tokenizers: the `semantic` extra). embed() -> unit float32 rows."""

    def __init__(self, d=None, name=None, threads=None):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        self.name = name or model_name()
        self.m = MODELS[self.name]
        d = Path(d) if d else model_dir(self.name)
        bad = verify(d, self.name)
        if bad:
            raise RuntimeError("; ".join(bad))
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self.tok.enable_truncation(MAX_TOKENS)
        self.tok.enable_padding(pad_id=0, pad_token="[PAD]")
        if hasattr(ort, "disable_telemetry_events"):
            ort.disable_telemetry_events()
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads or os.environ.get("GARAGE_EMBED_THREADS") or 2)
        so.inter_op_num_threads = 1
        so.log_severity_level = 3
        so.enable_cpu_mem_arena = False   # the arena keeps each batch's peak for good (1.2 GB after a full build)
        self.sess = ort.InferenceSession(str(d / self.m["onnx"]), so, providers=["CPUExecutionProvider"])

    def embed(self, texts, batch=16):
        np = self.np
        out = []
        for i in range(0, len(texts), batch):
            enc = self.tok.encode_batch([t or " " for t in texts[i:i + batch]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            h = self.sess.run(None, {"input_ids": ids, "attention_mask": mask,
                                     "token_type_ids": np.zeros_like(ids)})[0]
            if self.m["pool"] == "cls":
                v = h[:, 0]
            else:
                mf = mask[..., None].astype(np.float32)
                v = (h * mf).sum(1) / np.maximum(mf.sum(1), 1e-9)
            out.append(v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9))
        return np.concatenate(out).astype(np.float32) if out else np.zeros((0, self.m["dim"]), np.float32)

    def query(self, q):
        return [float(x) for x in self.embed([self.m["query_prefix"] + q])[0]]


# ---- vectors in the index: int8 (cosine within ~1% of float32), with their norm -------------------------------------

VEC_SCHEMA = "create table vec (id integer primary key, key text, v blob, n real)"


def row_text(src, title, name, tags, note, body):
    if src == "topic":
        return f"{title}. {note} {body}"
    if src == "resource":
        return f"{name}: {note} ({body})"
    return f"{name}: {body}"


def text_key(text, name=None):
    return hashlib.sha1(f"{name or model_name()}\0{text}".encode()).hexdigest()


def pack(v):
    return array.array("b", (max(-127, min(127, round(float(x) * 127.0))) for x in v)).tobytes()


def _norm(blob):
    return math.sqrt(sum(x * x for x in array.array("b", blob))) or 1.0


def _old_vectors(old_db, name):
    try:
        o = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True, timeout=5)
        try:
            row = o.execute("select v from meta where k = 'vec_model'").fetchone()
            if not row or row[0] != name:
                return {}
            return {k: v for k, v in o.execute("select key, v from vec")}
        finally:
            o.close()
    except sqlite3.Error:
        return {}


def attach(c, old_db=None, embed_max=None, log=None):
    """Vectors for the index being built (connection c): the old index's when a topic's text is unchanged, else
    embedded (by the service, or in this process with GARAGE_SEMANTIC=local), at most `embed_max` new ones (None =
    all). A topic left without one is still found by its words. No vector at all: no `vec` table. -> stats."""
    if mode() == "off":
        return {}
    name = model_name()
    rows = c.execute("select d.id, d.src, f.title, f.name, f.tags, f.note, f.body from docs d join docs_fts f on "
                     f"f.rowid = d.id where d.src in ({','.join('?' * len(SRCS))}) order by d.id", SRCS).fetchall()
    keyed = [(r[0], text_key(t, name), t) for r in rows for t in [row_text(*r[1:])]]
    old = _old_vectors(old_db, name) if old_db and Path(old_db).exists() else {}
    have = {k: old[k] for _, k, _ in keyed if k in old}
    need = list({k: t for _, k, t in keyed if k not in have}.items())
    if embed_max is not None:
        need = need[:embed_max]
    t0, made, how = time.time(), 0, ""
    if need:
        emb = None
        if mode() == "local":
            emb, how = _local(), "local"
        elif ask({"op": "ping"}, timeout=TIMEOUT if embed_max is not None else 15):   # (socket activation: ~1 s)
            how = "service"
        for i in range(0, len(need) if how else 0, MAX_TEXTS):
            part = need[i:i + MAX_TEXTS]
            try:
                blobs = [pack(v) for v in emb.embed([t for _, t in part])] if emb else _ask_embed([t for _, t in part])
            except (OSError, ValueError, RuntimeError) as e:
                if log:
                    log(f"semantic: embedding stopped: {e}")
                break
            have.update((k, b) for (k, _), b in zip(part, blobs))
            made += len(part)
    vec = [(i, k, have[k], _norm(have[k])) for i, k, _ in keyed if k in have]
    if not vec:
        return {"vectors": 0}
    c.execute(VEC_SCHEMA)
    with c:
        c.executemany("insert into vec values (?,?,?,?)", vec)
        c.execute("insert or replace into meta values ('vec_model', ?)", (name,))
    out = {"vectors": len(vec), "vectors_new": made}
    if made:
        out.update(embed_seconds=round(time.time() - t0, 1), embedded_by=how)
    return out


# ---- query time --------------------------------------------------------------------------------------------------

def ask(req, timeout=TIMEOUT, path=None):
    """One request to the service -> its reply dict, or None (no service, too slow, an error)."""
    path = str(path or socket_path())
    if not os.path.exists(path):
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except OSError:
        return None
    try:
        s.settimeout(timeout)
        s.connect(path)
        s.sendall(json.dumps(req).encode() + b"\n")
        buf = bytearray()
        while not buf.endswith(b"\n") and len(buf) < 16 * MAX_REQUEST:
            b = s.recv(1 << 16)
            if not b:
                break
            buf += b
        out = json.loads(buf)
        return out if isinstance(out, dict) and not out.get("error") else None
    except (OSError, ValueError):
        return None
    finally:
        s.close()


def _ask_embed(texts):
    r = ask({"op": "embed", "texts": texts, "model": model_name()}, timeout=120)
    if not r or r.get("model") != model_name():
        raise RuntimeError("the embedding service did not answer")
    raw = base64.b64decode(r["v"])
    d = MODELS[model_name()]["dim"]
    if len(raw) != d * len(texts):
        raise ValueError("bad vector size from the service")
    return [raw[i * d:(i + 1) * d] for i in range(len(texts))]


_local_state = {}


def _local():
    if "emb" not in _local_state:
        _local_state["emb"] = Embedder()
    return _local_state["emb"]


def _query_vector(q, name):
    if mode() == "local":
        emb = _local()
        return emb.query(q) if emb.name == name else None
    r = ask({"op": "query", "q": q, "model": name})
    v = r.get("v") if r and r.get("model") == name else None
    return v if isinstance(v, list) and len(v) == MODELS[name]["dim"] else None


_vecs = {}   # (database file, mtime, size) -> [(docid, int8 array, norm)]: decoded once per process and index file


def _vectors(c):
    try:
        name = c.execute("select v from meta where k = 'vec_model'").fetchone()
        db = next((f for _, n, f in c.execute("pragma database_list") if n == "main"), "")
    except sqlite3.Error:
        return None, []
    if not name or name[0] not in MODELS:
        return None, []
    try:
        st = os.stat(db) if db else None
    except OSError:
        st = None
    key = (db, st.st_mtime_ns, st.st_size) if st else None
    if key and key in _vecs:
        return name[0], _vecs[key]
    try:
        rows = [(i, array.array("b", v), n) for i, v, n in c.execute("select id, v, n from vec")]
    except sqlite3.Error:
        return None, []
    if key:
        _vecs.clear()
        _vecs[key] = rows
    return name[0], rows


def vector_hits(c, q, k=100):
    """[(docid, cosine)] of the topics nearest to the query in index c, best first; [] when semantic search is off,
    the index has no vectors, or nothing answers within TIMEOUT."""
    q = str(q).strip()[:1000]
    if mode() == "off" or not q:
        return []
    name, rows = _vectors(c)
    if not rows:
        return []
    qv = _query_vector(q, name)
    if not qv:
        return []
    dot = getattr(math, "sumprod", None) or (lambda a, b: sum(map(operator.mul, a, b)))   # sumprod: 3.12+, 2x
    sims = [(i, dot(v, qv) / n) for i, v, n in rows]
    sims.sort(key=lambda x: -x[1])
    return sims[:k]


# ---- the service: one JSON line in, one out, over a unix socket. It reads no files but the model. ------------------

def handle(req, emb):
    op = req.get("op")
    if req.get("model", emb.name) != emb.name:
        return {"error": f"this service runs {emb.name}"}
    if op == "ping":
        return {"ok": True, "model": emb.name, "rss_kb": _rss_kb()}
    if op == "query":
        q = req.get("q")
        if not isinstance(q, str):
            return {"error": "query: q, a string"}
        return {"model": emb.name, "v": [round(x, 5) for x in emb.query(q[:1000])]}
    if op == "embed":
        texts = req.get("texts")
        if not isinstance(texts, list) or len(texts) > MAX_TEXTS or not all(isinstance(t, str) for t in texts):
            return {"error": f"embed: texts, a list of at most {MAX_TEXTS} strings"}
        v = emb.embed([t[:4000] for t in texts])
        return {"model": emb.name, "v": base64.b64encode(b"".join(pack(x) for x in v)).decode()}
    return {"error": "op: ping | query | embed"}


def _rss_kb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def serve(sock=None, idle=None, emb=None, ready=None):
    """Load the model once and answer on a unix socket: the one systemd hands over (socket activation, LISTEN_FDS),
    else `sock` (created mode 0666). With `idle` seconds, exit after that long without a request (systemd starts it
    again on the next one). `emb` and `ready` (called with the server) are for tests."""
    import socketserver
    import threading
    emb = emb or Embedder()
    last = [time.time()]
    busy = threading.Semaphore(4)

    class H(socketserver.StreamRequestHandler):
        def handle(self):
            last[0] = time.time()
            self.connection.settimeout(30)
            with busy:
                try:
                    req = json.loads(self.rfile.readline(MAX_REQUEST))
                    out = handle(req, emb) if isinstance(req, dict) else {"error": "a JSON object, one line"}
                except Exception as e:   # noqa: BLE001 - one bad request never stops the service
                    out = {"error": str(e)[:200]}
            try:
                self.wfile.write(json.dumps(out, separators=(",", ":")).encode() + b"\n")
            except OSError:
                pass
            last[0] = time.time()

    class S(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    if os.environ.get("LISTEN_FDS") == "1" and os.environ.get("LISTEN_PID") == str(os.getpid()):
        srv = S(None, H, bind_and_activate=False)
        srv.socket = socket.socket(fileno=3)
    else:
        sock = Path(sock) if sock else socket_path()
        sock.parent.mkdir(parents=True, exist_ok=True)
        sock.unlink(missing_ok=True)
        srv = S(str(sock), H)
        os.chmod(sock, 0o666)
    if idle:
        def watch():
            while time.time() - last[0] < idle:
                time.sleep(min(10, idle))
            srv.shutdown()
        threading.Thread(target=watch, daemon=True).start()
    if ready:
        ready(srv)
    else:
        print(f"garage-embed: {emb.name} ready, {_rss_kb() // 1024} MB", flush=True)
    srv.serve_forever()
    srv.server_close()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m garage.semantic", description="search by meaning: model, service")
    ap.add_argument("cmd", choices=["fetch", "verify", "serve", "status"])
    ap.add_argument("--dir", help="model folder (default: $GARAGE_MODELS or /opt/garage/models, /NAME/REVISION)")
    ap.add_argument("--socket", help=f"default {socket_path()}")
    ap.add_argument("--idle", type=int, default=0, help="serve: exit after this many seconds without a request")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        print(fetch(a.dir))
        return 0
    if a.cmd == "verify":
        bad = verify(a.dir)
        print("\n".join(bad) or f"ok {a.dir or model_dir()}")
        return 1 if bad else 0
    if a.cmd == "status":
        r = ask({"op": "ping"}, timeout=5, path=a.socket)
        print(json.dumps(r) if r else f"no service at {a.socket or socket_path()}")
        return 0 if r else 1
    serve(a.socket, a.idle or None)
    return 0


def health():
    if mode() == "off":
        return [("PASS", "search by meaning off (GARAGE_SEMANTIC=0)")]
    if mode() == "local":
        bad = verify()
        return [("FAIL" if bad else "PASS", "; ".join(bad) or f"search by meaning: model in this process "
                 f"({model_dir()})")]
    if not socket_path().exists():
        return []   # not set up here (the Mac, uvx): nothing to report
    r = ask({"op": "ping"}, timeout=5)
    if r:
        return [("PASS", f"search by meaning: {socket_path()} ({r.get('model')}, {r.get('rss_kb', 0) // 1024} MB)")]
    return [("WAIT", f"search by meaning: {socket_path()} does not answer (keyword search only)")]


if __name__ == "__main__":
    sys.exit(main())
