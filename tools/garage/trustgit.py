"""Trust write-back: what `garage review` / `garage promote` write to $GARAGE_REPO/trust/registry.yaml goes to git.

  publish(changes, message, repo=None) -> (status, text)
      changes = {rid: the record now written | None (removed)}; message = "trust: <rid> → <tier> (<who>)"
      status: pushed | committed (kept locally, pushed later) | unchanged | not-git | off | error

When $GARAGE_REPO is a git clone: commit trust/registry.yaml and only that file (other staged or modified files are
left exactly as they are), as "garage", then push to the branch's upstream with the user's own git credentials (on the
server: user garage's gh login, `gh auth setup-git`). A rejected push fetches and rebases (--autostash); if the rebase
conflicts (or a clean line merge left records that don't match upstream's pins), it is aborted and the commit is
replayed on upstream's registry: upstream's file plus these records, except
a record whose sha no longer matches upstream's pin (a pin bump won; that review must be redone). Nothing is ever
reset, force-pushed or discarded. Not a git clone (an `install.sh --src` copy): the file is written and one warning
line says the change isn't in git. GARAGE_TRUST_GIT=0 turns the git step off (same warning).
garage-sync pulls with `git pull --rebase --autostash`, so a local trust commit that couldn't be pushed yet survives
and goes out with the next publish.
"""
import fcntl
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import paths

REL = "trust/registry.yaml"
PINS_REL = "lock/pins.yaml"
TRIES = 3


def _identity():
    return (os.environ.get("GARAGE_GIT_NAME") or "garage", os.environ.get("GARAGE_GIT_EMAIL") or "garage@localhost")


def git(repo, *args, inp=None, env=None, timeout=180):
    name, email = _identity()
    e = dict(os.environ, GIT_TERMINAL_PROMPT="0", **(env or {}))
    return subprocess.run(["git", "-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "core.hooksPath=/dev/null",
                           "-C", str(repo), *args], capture_output=True, text=True, input=inp, env=e, timeout=timeout)


def _out(p):
    return (p.stderr or p.stdout or "").strip().splitlines()[-1:] or [""]


def is_clone(repo):
    """True when repo is the top of its own git work tree (not a folder inside some other repository)."""
    repo = Path(repo)
    if not (repo / ".git").exists():
        return False
    p = git(repo, "rev-parse", "--show-toplevel")
    return p.returncode == 0 and Path(p.stdout.strip()).resolve() == repo.resolve()


def warn(text):
    print(f"garage: {text}", file=sys.stderr)


def _busy(repo):
    gd = git(repo, "rev-parse", "--git-dir").stdout.strip()
    g = Path(gd) if os.path.isabs(gd) else Path(repo) / gd
    return any((g / x).exists() for x in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD"))


def _yaml_at(repo, rev, rel):
    import yaml
    p = git(repo, "show", f"{rev}:{rel}")
    if p.returncode != 0:
        return {}
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    data = yaml.load(p.stdout, Loader=loader) or {}
    return data if isinstance(data, dict) else {}


def _ok(rid, rec, reg, pins):
    if rec is None:
        return rid not in reg
    pin = pins.get(rid) or {}
    return reg.get(rid) == rec and (rec.get("trust") == "quarantine" or not pins or pin.get("sha") == rec.get("sha"))


def consistent(repo, changes):
    """After a clean textual rebase: HEAD holds exactly these records and their pins still match (a line merge can
    keep a record whose pin upstream just moved, or mix two versions of one record)."""
    from . import trust as trust_mod
    reg = {str(k): trust_mod._norm(v) for k, v in _yaml_at(repo, "HEAD", REL).items()}
    pins = _yaml_at(repo, "HEAD", PINS_REL)
    return all(_ok(rid, trust_mod._norm(rec) if rec else None, reg, pins) for rid, rec in changes.items())


def replay(repo, changes, message, upstream):
    """A new commit on `upstream` = upstream's registry + these records; the branch moves there (reset --keep, which
    refuses rather than overwrite local modifications). -> (ok, skipped rids)"""
    from . import trust as trust_mod
    reg = {str(k): trust_mod._norm(v) for k, v in _yaml_at(repo, upstream, REL).items()}
    pins = _yaml_at(repo, upstream, PINS_REL)
    skipped = []
    for rid, rec in changes.items():
        if rec is None:
            reg.pop(rid, None)
            continue
        pin = pins.get(rid) or {}
        if rec.get("trust") != "quarantine" and pins and pin.get("sha") != rec.get("sha"):
            skipped.append(rid)   # upstream moved the pin meanwhile: its (reset) record wins
            continue
        reg[rid] = rec
    blob = git(repo, "hash-object", "-w", "--stdin", inp=trust_mod._dump(reg))
    if blob.returncode != 0:
        return False, skipped
    with tempfile.TemporaryDirectory() as td:
        env = {"GIT_INDEX_FILE": os.path.join(td, "index")}
        steps = [("read-tree", upstream),
                 ("update-index", "--add", "--cacheinfo", f"100644,{blob.stdout.strip()},{REL}")]
        for s in steps:
            if git(repo, *s, env=env).returncode != 0:
                return False, skipped
        tree = git(repo, "write-tree", env=env)
    if tree.returncode != 0:
        return False, skipped
    if tree.stdout.strip() == git(repo, "rev-parse", f"{upstream}^{{tree}}").stdout.strip():
        return git(repo, "reset", "-q", "--keep", upstream).returncode == 0, skipped   # nothing of ours left
    note = ("\n\nNot applied (upstream moved the pin): " + ", ".join(skipped)) if skipped else ""
    c = git(repo, "commit-tree", tree.stdout.strip(), "-p", upstream, "-m", message + note)
    if c.returncode != 0:
        return False, skipped
    k = git(repo, "reset", "-q", "--keep", c.stdout.strip())
    return k.returncode == 0, skipped


def _push(repo, changes, message):
    up = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if up.returncode != 0 or "/" not in up.stdout:
        return "committed", "committed locally; the branch has no upstream to push to"
    upstream = up.stdout.strip()
    remote, _, branch = upstream.partition("/")
    last = ""
    for _ in range(TRIES):
        p = git(repo, "push", "-q", remote, f"HEAD:{branch}")
        if p.returncode == 0:
            return "pushed", f"pushed to {upstream}"
        last = _out(p)[0]
        f = git(repo, "fetch", "-q", remote, branch)
        if f.returncode != 0:
            return "committed", f"committed locally, push failed ({last}); the next publish or garage-sync sends it"
        r = git(repo, "rebase", "-q", "--autostash", upstream)
        if r.returncode != 0:
            git(repo, "rebase", "--abort")
        if r.returncode != 0 or not consistent(repo, changes):
            ok, skipped = replay(repo, changes, message, upstream)
            if not ok:
                return "committed", (f"committed locally; rebase on {upstream} conflicted and the replay failed: "
                                     "resolve by hand (nothing was discarded)")
            if skipped:
                warn(f"upstream moved the pin of {', '.join(skipped)}: those records were not applied (review again)")
    return "committed", f"committed locally, push still rejected after {TRIES} tries ({last})"


def publish(changes, message, repo=None):
    repo = Path(repo or paths.repo())
    if os.environ.get("GARAGE_TRUST_GIT", "") == "0":
        warn(f"{REL} written; GARAGE_TRUST_GIT=0: the change isn't in git")
        return "off", "git step off"
    if not is_clone(repo):
        warn(f"{REL} written, but {repo} is not a git clone (a --src copy): the change isn't in git")
        return "not-git", "not a git clone"
    try:
        gd = Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip() or repo / ".git")
        with open(gd / "garage-trust.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            if git(repo, "rev-parse", "-q", "--verify", "HEAD").returncode != 0:
                warn(f"{REL} written, but {repo} has no commits yet: not committed")
                return "error", "no commits"
            if _busy(repo):
                warn(f"{REL} written, but {repo} is in the middle of a rebase/merge: not committed")
                return "error", "repository busy"
            a = git(repo, "add", "--", REL)
            if a.returncode != 0:
                warn(f"{REL} written, git add failed: {_out(a)[0]}")
                return "error", "git add failed"
            if git(repo, "diff", "--cached", "--quiet", "HEAD", "--", REL).returncode == 0:
                return "unchanged", "registry unchanged"
            c = git(repo, "commit", "-q", "--only", "-m", message, "--", REL)
            if c.returncode != 0:
                warn(f"{REL} written, git commit failed: {_out(c)[0]}")
                return "error", "git commit failed"
            status, text = _push(repo, changes, message)
    except (OSError, subprocess.SubprocessError) as e:
        warn(f"{REL} written, git step failed: {e}")
        return "error", str(e)
    if status != "pushed":
        warn(f"trust change {text}")
    return status, text


def message(rids, tier, who):
    rids = list(rids)
    head = rids[0] if len(rids) == 1 else f"{len(rids)} items"
    msg = f"trust: {head} → {tier} ({who})"
    return msg + ("\n\n" + "\n".join(rids) if len(rids) > 1 else "")
