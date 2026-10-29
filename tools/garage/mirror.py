"""`garage mirror`: the local mirror of every pinned snapshot ($GARAGE_HOME/mirror, $GARAGE_HOME/quarantine).

Layout (both roots are nested btrfs subvolumes, so snapper's @apps snapshots skip them):
  <root>/<owner>__<repo>/<sha12>/          the files of the pinned commit (no .git), only what the policy keeps
  <root>/<owner>__<repo>/<sha12>/.garage.json   repo, url, sha, path(s), pinned, licence, size, sha256 manifest
  <root>/<owner>__<repo>/current          -> the newest <sha12> in that root
Root = quarantine/ when the unit holds a runnable resource whose trust tier is quarantine (garage.trust.tier; without
the trust module every runnable item counts as quarantine), else mirror/. Each run moves units whose tier changed.

A unit is one (repo, sha): every pinned resource of that repo shares it. What a unit keeps:
  snapshot, path ''      the whole tree
  snapshot, path given   only those folders/files (blobless + sparse fetch: a giant repo costs only its sub-folder)
  readme                 README*, LICENSE*/COPYING*/NOTICE*, llms.txt, docs/ and doc/ (pruned to <= 5 MB)
  link                   nothing
Every unit keeps the repo's root LICENSE/COPYING/NOTICE files. Dropped on the way in (and listed in .garage.json
"excluded"): known payload folders (DANGEROUS), archives/binaries > 1 MB, any file > 20 MB, symlinks leading outside
the snapshot. In quarantine/ the exec bits are stripped (restored from the manifest when a unit is promoted).

Engines: "git" (default; `git fetch --depth 1 [--filter=blob:none] origin <sha>` + sparse checkout, exactly one commit)
and "vendir" (Carvel vendir, whole-tree units only, falls back to git). vendir 0.46.3 with `ref: <sha>, depth: 1`
runs `git fetch origin --depth 1` with tagOpt --tags (the tip of every branch and tag), inits submodules unless told
not to, keeps .git, downloads the whole tree before includePaths, and fails for a sha that is no longer a branch/tag
tip ("unable to read tree") -- so it can't be the default once pins age. state/vendir/vendir.yml is still generated
from the pins on every run (the portable, declarative description of the mirror).

API: local_path(rid) -> str|None, fetch(rid, dest) -> str, units(), check() -> [problems], health().
Mirrored content is untrusted data: nothing here executes, imports or installs anything from it.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

from . import catalog as catalog_mod
from . import paths
from . import pins as pins_mod

LICENSE_PATTERNS = ["/[Ll][Ii][Cc][Ee][Nn][CcSs][Ee]*", "/[Cc][Oo][Pp][Yy][Ii][Nn][Gg]*", "/[Nn][Oo][Tt][Ii][Cc][Ee]*"]
README_PATTERNS = ["/[Rr][Ee][Aa][Dd][Mm][Ee]*", "/llms.txt"]
DOCS_PATTERNS = ["/docs/", "/doc/"]
LICENSE_PREFIXES = ("license", "licence", "copying", "notice")
README_CAP = 5 * 1024 * 1024
FILE_CAP = 20 * 1024 * 1024
BINARY_CAP = 1024 * 1024
BINARY_EXT = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".zst", ".lz4", ".jar", ".war", ".apk",
              ".ipa", ".dmg", ".iso", ".img", ".deb", ".rpm", ".msi", ".exe", ".dll", ".so", ".dylib", ".bin", ".o",
              ".a", ".pyc", ".class", ".wasm", ".node", ".pdb", ".lib", ".pak", ".dat", ".onnx", ".pt", ".pth",
              ".safetensors", ".gguf", ".h5", ".ckpt", ".parquet", ".sqlite", ".db", ".mp4", ".mov", ".webm",
              ".mkv", ".avi", ".mp3", ".wav", ".flac", ".psd"}
# Folders that are attack payloads, not code to read: never mirrored (any depth, case-insensitive) ...
DANGEROUS_NAMES = {"web-shells", "webshells"}
# ... and per repo (owner/name lowercase -> folder paths from the repo root)
DANGEROUS = {
    "danielmiessler/seclists": ["Web-Shells", "Payloads"],
    "swisskyrepo/payloadsallthethings": ["Upload Insecure Files"],
}
ENGINES = ("git", "vendir")
META = ".garage.json"
VENDIR = os.environ.get("GARAGE_VENDIR", "vendir")
GIT_TIMEOUT = 3600


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def git_base():
    return os.environ.get("GARAGE_GIT_BASE", "https://github.com/").rstrip("/") + "/"


def repo_url(repo):
    return git_base() + repo


def slug(repo):
    return repo.lower().replace("/", "__")


def roots():
    return {"mirror": paths.mirror(), "quarantine": paths.quarantine()}


# ---- trust ----------------------------------------------------------------------------------------------------------

def _trust():
    try:
        from . import trust
        return trust
    except ImportError:
        return None


def tier(rid, res):
    """quarantine | reviewed | trusted for runnable items, n/a otherwise. No trust module -> quarantine."""
    if not catalog_mod.is_runnable(res):
        return "n/a"
    t = _trust()
    if t is None:
        return "quarantine"
    try:
        return t.tier(rid)
    except Exception:   # noqa: BLE001 - a broken registry must fail closed, not open
        return "quarantine"


# ---- units ----------------------------------------------------------------------------------------------------------

def _escape(p):
    out = []
    for ch in p:
        out.append("\\" + ch if ch in "*?[]\\!#" else ch)
    return "".join(out)


def units(pins=None, cat=None):
    """[(repo, sha) unit dicts] for every pin that keeps something local."""
    pins = pins_mod.load() if pins is None else pins
    cat = catalog_mod.load() if cat is None else cat
    res_of = cat["resources"]
    out = {}
    for rid, p in sorted(pins.items()):
        if p["policy"] == "link":
            continue
        res = res_of.get(rid, {})
        key = (p["repo"].lower(), p["sha"])
        u = out.setdefault(key, {"repo": p["repo"], "sha": p["sha"], "rids": [], "paths": set(), "full": False,
                                 "docs": False, "snapshot": False, "pinned": p["pinned"],
                                 "license_at_pin": p["license_at_pin"], "size_kb": p["size_kb"],
                                 "license": pins_mod.effective_license(p["license_at_pin"], res.get("license")),
                                 "quarantine": False, "tiers": {}})
        u["rids"].append(rid)
        u["pinned"] = max(u["pinned"], p["pinned"])
        if p["policy"] == "snapshot":
            u["snapshot"] = True
            if p["path"]:
                u["paths"].add(p["path"])
            else:
                u["full"] = True
        else:
            u["docs"] = True
        t = tier(rid, res)
        u["tiers"][rid] = t
        if t == "quarantine":
            u["quarantine"] = True
    for u in out.values():
        ps = sorted(u["paths"])   # drop paths inside another one: skills/pdf is in skills
        u["paths"] = [] if u["full"] else [p for p in ps if not any(p.startswith(q + "/") for q in ps)]
        u["policy"] = "snapshot" if u["snapshot"] else "readme"
        if u["docs"] and u["size_kb"] > pins_mod.GIANT_KB and not u["full"]:
            u["docs"] = False   # a giant repo's docs/ is thousands of files (ClickHouse: 111 s for 5 MB): README only
        u["location"] = "quarantine" if u["quarantine"] else "mirror"
        u["patterns"] = patterns(u)
    return list(out.values())


def patterns(u):
    """sparse-checkout patterns (gitignore syntax, --no-cone) or [] for the whole tree."""
    if u["full"]:
        return []
    pats = LICENSE_PATTERNS + README_PATTERNS + (DOCS_PATTERNS if u["docs"] else [])
    pats += ["/" + _escape(p.strip("/")) for p in u["paths"]]
    return pats


def unit_dir(root, repo, sha):
    return Path(root) / slug(repo) / sha[:12]


def read_meta(d):
    try:
        with open(Path(d) / META, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def find_unit(repo, sha):
    """(location, dir) of a complete unit, else (None, None)."""
    for loc, root in roots().items():
        d = unit_dir(root, repo, sha)
        m = read_meta(d)
        if m and m.get("sha") == sha:
            return loc, d
    return None, None


# ---- fetching -------------------------------------------------------------------------------------------------------

def git_env():
    env = dict(os.environ)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
               GIT_LFS_SKIP_SMUDGE="1", GIT_ASKPASS="true", SSH_ASKPASS="true")
    return env


def git(work, *args, timeout=GIT_TIMEOUT, inp=None):
    cfg = ["-c", "protocol.allow=never", "-c", "protocol.https.allow=always", "-c", "core.hooksPath=/dev/null",
           "-c", "advice.detachedHead=false", "-c", "init.templateDir=", "-c", "core.fsmonitor=false",
           "-c", "submodule.recurse=false", "-c", "fetch.recurseSubmodules=false", "-c", "gc.auto=0",
           "-c", "maintenance.auto=false"]
    if git_base().startswith("file://"):
        cfg += ["-c", "protocol.file.allow=always"]
    p = subprocess.run(["git", *cfg, "-C", str(work), *args], capture_output=True, text=True, env=git_env(),
                       timeout=timeout, input=inp)
    if p.returncode != 0:
        raise RuntimeError(f"git {args[0]}: {(p.stderr or p.stdout).strip()[-400:]}")
    return p.stdout


def git_fetch(repo, sha, pats, work):
    """Fetch exactly one commit into work/ (a fresh dir) and check it out; work/.git is removed after."""
    work = Path(work)
    work.mkdir(parents=True)
    git(work, "init", "-q")
    git(work, "remote", "add", "origin", repo_url(repo))
    filt = ["--filter=blob:none"] if pats else []
    git(work, "fetch", "-q", "--no-tags", "--no-write-fetch-head", "--depth", "1", *filt, "origin", sha)
    got = git(work, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}").strip()
    if got != sha:
        raise RuntimeError(f"sha mismatch: asked {sha}, got {got or 'nothing'}")
    if pats:
        git(work, "sparse-checkout", "set", "--no-cone", "--stdin", inp="\n".join(pats) + "\n")
    git(work, "checkout", "-q", "--no-recurse-submodules", sha)
    head = git(work, "rev-parse", "HEAD").strip()
    if head != sha:
        raise RuntimeError(f"sha mismatch after checkout: {head}")
    shutil.rmtree(work / ".git")


def vendir_entry(u, path):
    git_ = {"url": repo_url(u["repo"]), "ref": u["sha"], "depth": 1, "skipInitSubmodules": True,
            "lfsSkipSmudge": True}
    c = {"path": ".", "lazy": True, "git": git_}
    inc = [p.lstrip("/").replace("\\", "") + ("**/*" if p.endswith("/") else "") for p in u["patterns"]]
    if inc:
        c["includePaths"] = inc
    exc = [f"{d}/**/*" for d in DANGEROUS.get(u["repo"].lower(), [])]
    if exc:
        c["excludePaths"] = exc
    return {"path": path, "contents": [c]}


def vendir_config(entries):
    return {"apiVersion": "vendir.k14s.io/v1alpha1", "kind": "Config", "directories": entries}


def vendir_fetch(u, work):
    """vendir sync of one whole-tree unit into work/; the lock's sha must equal the pin."""
    import yaml
    stage = Path(str(work) + ".vendir")
    stage.mkdir(parents=True)
    try:
        (stage / "vendir.yml").write_text(yaml.safe_dump(vendir_config([vendir_entry(u, "out")])))
        p = subprocess.run([VENDIR, "sync", "--chdir", str(stage), "-f", "vendir.yml", "--lock-file",
                            "vendir.lock.yml"], capture_output=True, text=True, env=git_env(), timeout=GIT_TIMEOUT)
        if p.returncode != 0:
            raise RuntimeError(f"vendir: {(p.stderr or p.stdout).strip()[-300:]}")
        lock = yaml.safe_load((stage / "vendir.lock.yml").read_text())
        got = lock["directories"][0]["contents"][0]["git"]["sha"]
        if got != u["sha"]:
            raise RuntimeError(f"sha mismatch: vendir locked {got}, pin is {u['sha']}")
        (stage / "out").rename(work)
        shutil.rmtree(Path(work) / ".git", ignore_errors=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# ---- sanitising -----------------------------------------------------------------------------------------------------

def _is_binary(path, name):
    if os.path.splitext(name)[1].lower() in BINARY_EXT:
        return True
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return True


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sanitize(top, repo, strip_exec, docs_cap=False):
    """Drop what must not be mirrored, fix modes, return (files manifest, excluded list)."""
    top = Path(top)
    danger = {d.lower().strip("/") for d in DANGEROUS.get(repo.lower(), [])}
    excluded = []

    def drop(p, reason):
        rel = str(p.relative_to(top))
        size = 0
        if p.is_dir() and not p.is_symlink():
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())
            shutil.rmtree(p)
        else:
            size = p.lstat().st_size
            p.unlink()
        excluded.append({"path": rel, "reason": reason, "bytes": size})

    real_top = top.resolve()
    for dirpath, dirnames, filenames in os.walk(top):
        d = Path(dirpath)
        for name in list(dirnames):
            p = d / name
            rel = str(p.relative_to(top)).lower()
            if name.lower() in DANGEROUS_NAMES or rel in danger:
                drop(p, "payload folder")
                dirnames.remove(name)
            elif p.is_symlink():
                filenames.append(name)
                dirnames.remove(name)
        for name in filenames:
            p = d / name
            if p.is_symlink():
                target = os.readlink(p)
                dest = (p.parent / target).resolve()
                if os.path.isabs(target) or not (dest == real_top or real_top in dest.parents):
                    drop(p, "symlink outside the snapshot")
                continue
            st = p.lstat()
            if not stat.S_ISREG(st.st_mode):
                drop(p, "not a regular file")
            elif st.st_size > FILE_CAP:
                drop(p, "file > 20 MB")
            elif st.st_size > BINARY_CAP and _is_binary(p, name):
                drop(p, "archive/binary > 1 MB")
    if docs_cap:
        _cap_docs(top, excluded)
    files = {}
    for dirpath, dirnames, filenames in os.walk(top):
        d = Path(dirpath)
        os.chmod(d, 0o755)
        for name in sorted(filenames + [n for n in dirnames if (d / n).is_symlink()]):
            p = d / name
            rel = str(p.relative_to(top))
            if rel == META:
                continue
            if p.is_symlink():
                files[rel] = ["link", os.readlink(p), 0]
                continue
            st = p.lstat()
            mode = 0o755 if st.st_mode & 0o111 else 0o644
            files[rel] = [_sha256(p), st.st_size, mode]
            os.chmod(p, 0o644 if strip_exec else mode)
    return files, excluded


def _cap_docs(top, excluded):
    """Units that keep docs/ for a readme pin: docs/ + doc/ <= README_CAP, the biggest files go first."""
    docs = sorted((p for p in top.rglob("*") if p.is_file() and not p.is_symlink()
                   and p.relative_to(top).parts[0].lower() in ("docs", "doc")), key=lambda p: -p.stat().st_size)
    total = sum(p.stat().st_size for p in docs)
    if total <= README_CAP:
        return
    for p in docs:
        if total <= README_CAP:
            break
        size = p.stat().st_size
        p.unlink()
        total -= size
        excluded.append({"path": str(p.relative_to(top)), "reason": "readme policy: docs over 5 MB", "bytes": size})


def manifest_sha(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def set_modes(top, files, strip_exec):
    for rel, (h, _, mode) in files.items():
        if h != "link":
            os.chmod(Path(top) / rel, 0o644 if strip_exec else mode)


# ---- placing --------------------------------------------------------------------------------------------------------

def _set_current(repo_dir):
    shas = []
    for d in Path(repo_dir).iterdir():
        if d.is_dir() and not d.is_symlink():
            m = read_meta(d)
            if m:
                shas.append((m.get("pinned", ""), m.get("fetched", ""), d.name))
    link = Path(repo_dir) / "current"
    if not shas:
        if link.is_symlink():
            link.unlink()
        return
    target = max(shas)[2]
    if link.is_symlink() and os.readlink(link) == target:
        return
    tmp = Path(repo_dir) / ".current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(target)
    tmp.replace(link)


def mirror_unit(u, engine="git"):
    """Fetch, sanitise and place one unit. Returns a result dict for the log."""
    root = roots()[u["location"]]
    final = unit_dir(root, u["repo"], u["sha"])
    tmpd = root / ".tmp"
    tmpd.mkdir(parents=True, exist_ok=True)
    work = tmpd / f"{slug(u['repo'])}__{u['sha'][:12]}.{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    t0 = time.monotonic()
    used = "git"
    try:
        if engine == "vendir" and u["full"] and shutil.which(VENDIR):
            try:
                vendir_fetch(u, work)
                used = "vendir"
            except Exception as e:   # noqa: BLE001 - the documented fallback
                log(f"  vendir failed for {u['repo']}@{u['sha'][:12]} ({e}); falling back to git fetch-by-sha")
                shutil.rmtree(work, ignore_errors=True)
                git_fetch(u["repo"], u["sha"], u["patterns"], work)
        else:
            git_fetch(u["repo"], u["sha"], u["patterns"], work)
        strip = u["location"] == "quarantine"
        files, excluded = sanitize(work, u["repo"], strip, docs_cap=u["docs"] and not u["full"])
        size = sum(v[1] for v in files.values() if v[0] != "link")
        meta = {
            "repo": u["repo"], "url": "https://github.com/" + u["repo"], "sha": u["sha"],
            "path": u["paths"][0] if len(u["paths"]) == 1 else "", "paths": u["paths"], "rids": u["rids"],
            "policy": u["policy"], "pinned": u["pinned"], "license": u["license"],
            "license_at_pin": u["license_at_pin"], "size_kb": u["size_kb"], "bytes": size, "files_count": len(files),
            "manifest_sha256": manifest_sha(files), "excluded": excluded, "engine": used, "fetched": now(),
            "location": u["location"], "exec_bits_stripped": strip, "tiers": u["tiers"], "patterns": u["patterns"],
            "files": files,
        }
        (work / META).write_text(json.dumps(meta, indent=1, sort_keys=False) + "\n", encoding="utf-8")
        os.chmod(work / META, 0o644)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(final.parent, 0o755)
        if final.exists():
            shutil.rmtree(final)   # an incomplete leftover (find_unit saw no matching .garage.json)
        work.rename(final)
        _set_current(final.parent)
        for loc, other in roots().items():   # a refetch (policy changed) may leave the old copy in the other root
            old = unit_dir(other, u["repo"], u["sha"])
            if loc != u["location"] and old.is_dir():
                shutil.rmtree(old)
                _set_current(old.parent)
                _rmdir_empty(old.parent)
        return {"repo": u["repo"], "sha": u["sha"], "ok": True, "location": u["location"], "engine": used,
                "bytes": size, "files": len(files), "excluded": len(excluded),
                "seconds": round(time.monotonic() - t0, 2)}
    except Exception as e:   # noqa: BLE001 - one bad repo never stops the run
        shutil.rmtree(work, ignore_errors=True)
        return {"repo": u["repo"], "sha": u["sha"], "ok": False, "error": str(e)[:400],
                "seconds": round(time.monotonic() - t0, 2)}


def _copy_tree(src, dst):
    """cp -a with reflinks (cheap across the two subvolumes of one btrfs filesystem)."""
    p = subprocess.run(["cp", "-a", "--reflink=auto", str(src), str(dst)], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"cp: {p.stderr.strip()[-300:]}")


def move_unit(u, src_dir):
    """Move a complete unit to the root its tier calls for (promotion, or back to quarantine)."""
    root = roots()[u["location"]]
    final = unit_dir(root, u["repo"], u["sha"])
    tmpd = root / ".tmp"
    tmpd.mkdir(parents=True, exist_ok=True)
    work = tmpd / f"{slug(u['repo'])}__{u['sha'][:12]}.move.{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    _copy_tree(src_dir, work)
    meta = read_meta(work)
    strip = u["location"] == "quarantine"
    set_modes(work, meta.get("files", {}), strip)
    meta.update(location=u["location"], exec_bits_stripped=strip, tiers=u["tiers"], moved=now())
    (work / META).write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        shutil.rmtree(final)
    work.rename(final)
    _set_current(final.parent)
    shutil.rmtree(src_dir)
    _set_current(Path(src_dir).parent)
    _rmdir_empty(Path(src_dir).parent)


def _rmdir_empty(repo_dir):
    try:
        left = [x for x in repo_dir.iterdir() if x.name != "current"]
        if not left:
            if (repo_dir / "current").is_symlink():
                (repo_dir / "current").unlink()
            repo_dir.rmdir()
    except OSError:
        pass


def promote(rid):
    """Move the unit holding rid to wherever its tier now says (T4's `garage promote` calls this after a review)."""
    p = pins_mod.get(rid)
    if not p:
        return None
    for u in units():
        if u["repo"].lower() == p["repo"].lower() and u["sha"] == p["sha"]:
            loc, d = find_unit(u["repo"], u["sha"])
            if d and loc != u["location"]:
                move_unit(u, d)
            return u["location"]
    return None


def prune(us):
    """Remove snapshots no pin refers to, and stale temp dirs."""
    keep = {(slug(u["repo"]), u["sha"][:12]) for u in us}
    removed = 0
    for root in roots().values():
        if not root.is_dir():
            continue
        shutil.rmtree(root / ".tmp", ignore_errors=True)
        for repo_dir in root.iterdir():
            if not repo_dir.is_dir() or repo_dir.name.startswith("."):
                continue
            for d in repo_dir.iterdir():
                if d.is_dir() and not d.is_symlink() and (repo_dir.name, d.name) not in keep:
                    shutil.rmtree(d)
                    removed += 1
            _set_current(repo_dir)
            _rmdir_empty(repo_dir)
    return removed


def write_vendir_yml(us):
    import yaml
    d = paths.state() / "vendir"
    d.mkdir(parents=True, exist_ok=True)
    home = paths.home()
    entries = [vendir_entry(u, str(unit_dir(roots()[u["location"]], u["repo"], u["sha"]).relative_to(home)))
               for u in us]
    f = d / "vendir.yml"
    f.write_text("# Generated by `garage mirror` from lock/pins.yaml; paths relative to $GARAGE_HOME.\n"
                 + yaml.safe_dump(vendir_config(entries), sort_keys=False), encoding="utf-8")
    return f


def select(us, only):
    if not only:
        return us
    want = set()
    for x in only:
        want.add(catalog_mod.normalize_url(x) if "://" in x else x.lower())
    return [u for u in us if u["repo"].lower() in want or any(r in want for r in u["rids"])]


# ---- API for `garage add` and search --------------------------------------------------------------------------------

def local_path(rid):
    """The mirrored folder (or file) of a resource, else None. readme units return the unit folder."""
    p = pins_mod.get(rid)
    if not p or p.get("policy") == "link":
        return None
    for root in roots().values():
        d = unit_dir(root, p["repo"], p["sha"])
        if (d / META).is_file():
            sub = d / p["path"] if p["path"] else d
            return str(sub if sub.exists() else d)
    return None


def _license_files(top):
    return [f for f in Path(top).iterdir() if f.is_file() and f.name.lower().startswith(LICENSE_PREFIXES)]


def _covers(meta, path):
    if meta.get("policy") != "snapshot":
        return False
    ps = meta.get("paths") or []
    return not ps or any(path == q or path.startswith(q.rstrip("/") + "/") for q in ps)


def fetch(rid, dest):
    """Copy the pinned snapshot of rid (its `path`, or the whole repo) into dest; keep LICENSE/NOTICE; write
    dest/.garage.json. Uses the local mirror when it holds the path, else fetches the pinned sha from GitHub into
    $GARAGE_HOME/cache (the Mac, anyone). Refuses items without a licence (link only)."""
    rid = catalog_mod.normalize_url(rid)
    p = pins_mod.get(rid)
    if not p:
        raise LookupError(f"{rid}: no pin (not a GitHub resource, or `garage pin` hasn't run)")
    res = catalog_mod.load()["resources"].get(rid, {})
    lic = pins_mod.effective_license(p["license_at_pin"], res.get("license"))
    if lic.lower() in pins_mod.NO_LICENCE:
        raise PermissionError(f"{rid}: no licence upstream: link only, nothing may be copied")
    dest = Path(dest)
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise FileExistsError(f"{dest} exists and is not empty")
    src, source = None, "mirror"
    loc, d = find_unit(p["repo"], p["sha"])
    if d and _covers(read_meta(d), p["path"]):
        src = d
    if src is None:
        src, source = _cached(p), "github"
    meta = read_meta(src) or {}
    modes = {k: v for k, v in (meta.get("files") or {}).items()}
    sub = src / p["path"] if p["path"] else src
    if not sub.exists():
        raise FileNotFoundError(f"{p['path']!r} is not in {p['repo']}@{p['sha'][:12]}")
    tmp = dest.parent / f".{dest.name}.garage-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    prefix = p["path"].strip("/")
    if sub.is_dir():
        shutil.copytree(sub, tmp, symlinks=True, ignore=shutil.ignore_patterns(META) if not prefix else None)
    else:
        tmp.mkdir(parents=True)
        shutil.copy2(sub, tmp / sub.name)
        prefix = str(Path(prefix).parent) if "/" in prefix else ""
    # modes from the manifest (quarantine copies have their exec bits stripped)
    for rel, (h, _, mode) in modes.items():
        if h == "link":
            continue
        if prefix and not rel.startswith(prefix + "/"):
            continue
        q = tmp / (rel[len(prefix) + 1:] if prefix else rel)
        if q.is_file():
            os.chmod(q, mode)
    kept = []
    if p["path"]:
        for f in _license_files(src):
            target = tmp / f.name
            if target.exists():
                if target.read_bytes() == f.read_bytes():
                    continue
                target = tmp / f"{f.name}.repo-root"
            shutil.copy2(f, target)
            kept.append(target.name)
    kept += [f.name for f in _license_files(tmp) if f.name not in kept]
    files, _ = sanitize(tmp, p["repo"], strip_exec=False)
    out = {"url": rid, "repo": p["repo"], "sha": p["sha"], "path": p["path"], "pinned": p["pinned"],
           "license": lic, "license_at_pin": p["license_at_pin"], "license_files": sorted(set(kept)),
           "fetched": now(), "source": source, "files_count": len(files), "manifest_sha256": manifest_sha(files),
           "files": files}
    (tmp / META).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    if dest.exists():
        dest.rmdir()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp.rename(dest)
    return str(dest)


def _cached(p):
    """The pinned sha of p's repo (only p's path + licence files) under $GARAGE_HOME/cache."""
    cache = paths.home() / "cache" / slug(p["repo"]) / p["sha"][:12]
    key = p["path"] or ""
    d = cache / (hashlib.sha256(key.encode()).hexdigest()[:8] if key else "full")
    m = read_meta(d)
    if m and m.get("sha") == p["sha"]:
        return d
    u = {"repo": p["repo"], "sha": p["sha"], "full": not p["path"], "docs": False, "paths": [p["path"]] if
         p["path"] else []}
    pats = patterns(u)
    work = Path(str(d) + f".tmp{os.getpid()}")
    shutil.rmtree(work, ignore_errors=True)
    git_fetch(p["repo"], p["sha"], pats, work)
    files, excluded = sanitize(work, p["repo"], strip_exec=False)
    (work / META).write_text(json.dumps({"repo": p["repo"], "sha": p["sha"], "paths": u["paths"],
                                         "policy": "snapshot", "fetched": now(), "excluded": excluded,
                                         "files": files}) + "\n", encoding="utf-8")
    if d.exists():
        shutil.rmtree(d)
    d.parent.mkdir(parents=True, exist_ok=True)
    work.rename(d)
    return d


# ---- check / health -------------------------------------------------------------------------------------------------

def check(deep=False, us=None):
    """Problems: units whose .garage.json sha differs from the pin, misplaced units, manifest mismatches (deep)."""
    us = units() if us is None else us
    want = {(slug(u["repo"]), u["sha"][:12]): u for u in us}
    probs = []
    for loc, root in roots().items():
        if not root.is_dir():
            continue
        for repo_dir in root.iterdir():
            if not repo_dir.is_dir() or repo_dir.name.startswith("."):
                continue
            for d in repo_dir.iterdir():
                if d.is_symlink() or not d.is_dir():
                    continue
                m = read_meta(d)
                u = want.get((repo_dir.name, d.name))
                if m is None:
                    probs.append(f"{d}: no {META} (incomplete)")
                elif u is None:
                    probs.append(f"{d}: not pinned any more (prune)")
                elif m.get("sha") != u["sha"]:
                    probs.append(f"{d}: sha mismatch: .garage.json {m.get('sha')} != pin {u['sha']}")
                elif loc != u["location"]:
                    probs.append(f"{d}: in {loc}/ but its tier says {u['location']}/")
                elif deep:
                    for rel, (h, size, _) in (m.get("files") or {}).items():
                        f = d / rel
                        if h == "link":
                            if not f.is_symlink() or os.readlink(f) != size:
                                probs.append(f"{d}: {rel} link changed")
                        elif not f.is_file() or f.stat().st_size != size or _sha256(f) != h:
                            probs.append(f"{d}: {rel} differs from the manifest")
                            break
    return probs


def health():
    out = []
    for loc, root in roots().items():
        if not root.is_dir():
            out.append(("WAIT", f"{loc}: {root} missing (infra/install.d/20-mirror.sh)"))
            continue
        n = sum(1 for r in root.iterdir() if r.is_dir() and not r.name.startswith("."))
        out.append(("PASS", f"{loc}: {n} repos in {root}"))
    if not shutil.which(VENDIR):
        out.append(("WAIT", "vendir not installed (optional engine)"))
    return out


# ---- CLI ------------------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="garage mirror", description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="+", metavar="RID|OWNER/NAME", help="only these units")
    ap.add_argument("--from", dest="from_file", metavar="FILE", help="read --only entries from a file, one per line")
    ap.add_argument("--limit", type=int, help="fetch at most N missing units")
    ap.add_argument("--engine", choices=ENGINES, default=os.environ.get("GARAGE_MIRROR_ENGINE", "git"))
    ap.add_argument("--dry-run", action="store_true", help="list what would be fetched, moved and pruned")
    ap.add_argument("--check", action="store_true", help="report sha mismatches and misplaced units, change nothing")
    ap.add_argument("--deep", action="store_true", help="with --check: re-hash every file against the manifest")
    ap.add_argument("--no-prune", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    only = list(a.only or [])
    if a.from_file:
        only += [x.strip() for x in Path(a.from_file).read_text().splitlines() if x.strip() and x[0] != "#"]
    all_units = units()
    if a.check:
        probs = check(deep=a.deep, us=all_units)
        for x in probs:
            print(x)
        print(f"{len(probs)} problems in the mirror", file=sys.stderr)
        return 1 if any("mismatch" in x or "differs" in x for x in probs) else 0
    for root in roots().values():
        if not root.is_dir():
            log(f"{root} is missing: run infra/install.d/20-mirror.sh (as root) first")
            return 2
    us = select(all_units, only)
    todo, moves = [], []
    for u in us:
        loc, d = find_unit(u["repo"], u["sha"])
        if d is None or read_meta(d).get("patterns") != u["patterns"]:
            todo.append(u)   # missing, or what the pins keep of it changed (policy/path) at the same sha
        elif loc != u["location"]:
            moves.append((u, d))
    if a.limit is not None:
        todo = todo[:a.limit]
    vy = write_vendir_yml(all_units) if not a.dry_run else None
    log(f"units {len(all_units)} ({len(us)} selected): {len(todo)} to fetch, {len(moves)} to move"
        + (f"; vendir.yml: {vy}" if vy else ""))
    if a.dry_run:
        for u in todo:
            print(f"fetch  {u['location']:10}  {u['repo']}@{u['sha'][:12]}  {u['policy']}"
                  + (f"  paths={','.join(u['paths'])}" if u["paths"] else ""))
        for u, d in moves:
            print(f"move   {d} -> {u['location']}/")
        return 0
    results = []
    logf = paths.state() / "mirror.jsonl"
    logf.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    for u, d in moves:
        move_unit(u, d)
        log(f"moved  {u['repo']}@{u['sha'][:12]} -> {u['location']}/")
    for i, u in enumerate(todo, 1):
        r = mirror_unit(u, a.engine)
        results.append(r)
        with open(logf, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(r, at=now())) + "\n")
        log(f"[{i}/{len(todo)}] {'ok  ' if r['ok'] else 'FAIL'} {u['repo']}@{u['sha'][:12]} {u['location']}"
            + (f" {r['bytes'] // 1024} KB {r['files']} files {r['seconds']} s" if r["ok"] else f" {r['error']}"))
    removed = 0
    if not only and a.limit is None and not a.no_prune:
        removed = prune(all_units)
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    summary = {"fetched": len(ok), "failed": len(bad), "moved": len(moves), "pruned": removed,
               "bytes": sum(r["bytes"] for r in ok), "seconds": round(time.monotonic() - t0, 1),
               "failures": [{"repo": r["repo"], "error": r["error"]} for r in bad]}
    if a.json:
        print(json.dumps(summary, indent=1))
    else:
        print(f"mirror: {len(ok)} fetched ({summary['bytes'] // 1024 // 1024} MB), {len(bad)} failed, "
              f"{len(moves)} moved, {removed} pruned in {summary['seconds']} s")
    if only:
        return 1 if bad else 0
    return 1 if bad and len(bad) > max(5, len(results) // 20) else 0


if __name__ == "__main__":
    sys.exit(main())
