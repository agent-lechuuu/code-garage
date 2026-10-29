"""`garage scan ID`: read-only safety scan of one pinned snapshot (in the mirror or quarantine). Nothing is executed.

  garage scan ID|URL [--json] [--quiet]     scan the item's snapshot at its pinned sha; report in
                                            $GARAGE_HOME/state/scans/<slug>/<sha12>.json
  garage scan --path DIR [--kind skill]     scan any folder (tests, a candidate before it is proposed); nothing stored

Scanners (all local, no keys, no network; each in a bubblewrap box: read-only filesystem, no network, private /tmp):
  skillspector   NVIDIA SkillSpector --no-llm (71 patterns, YARA, AST taint); per SKILL.md folder, else the whole item
  aguara         Aguara `scan` (Go, 190+ rules incl. hooks and settings inside an item); the item's own policy ignored
  gitleaks       secrets (detect --no-git)
  mcp-scanner    Cisco mcp-scanner YARA mode on the tool descriptions found in an MCP server's source (static, no run)
  garage-checks  our own checks (research/system-design.md section 4): invisible/bidi/tag Unicode, encoded blobs,
                 override phrases, runtime instruction fetches, curl|sh, install hooks, persistence, oversized files,
                 binaries/minified/archives, hooks/.mcp.json/settings inside the item, scanner-suppression files,
                 symlinks out of the item, allowed-tools breadth, dependencies without a lockfile
Result per scanner: pass | warn | fail | skipped (not installed / not applicable) | error. Exit 1 when any scanner
fails, 2 on errors locating the item. Scanners: $GARAGE_SCANNERS (default /opt/garage/scanners, made by
infra/install.d/30-safety.sh) or the same tools on PATH; GARAGE_SCAN_SANDBOX=0 runs them without bubblewrap.
"""
import argparse
import base64
import binascii
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import paths

SCANNERS = Path(os.environ.get("GARAGE_SCANNERS", "/opt/garage/scanners"))
REQUIRED = ("skillspector", "aguara", "gitleaks", "garage-checks")   # must have run for an item to be reviewed
CHECKS_VERSION = "1"
TIMEOUT = 900
MAX_READ = 2_000_000
TEXT_BIG = 1_000_000
ITEM_BIG = 10_000_000
MAX_SKILL_DIRS = 60

# ---- locating the item --------------------------------------------------------------------------------------------


def _catalog():
    from . import catalog
    return catalog


def resolve(ident):
    """ID (rid/URL, owner/repo[/path], a resource name, or a topic id with one runnable resource) -> (rid, res)."""
    catalog = _catalog()
    cat = catalog.load()
    res = cat["resources"]
    s = str(ident).strip()
    if re.match(r"^https?://", s):
        rid = catalog.normalize_url(s)
        return rid, res.get(rid)
    if "/" in s:   # owner/repo[/tree/<ref>/path] or github.com/owner/repo
        rid = catalog.normalize_url("https://github.com/" + s.removeprefix("github.com/"))
        if rid in res:
            return rid, res[rid]
    low = s.lower()
    named = [r for r, x in res.items() if str(x.get("name", "")).lower() == low and catalog.is_runnable(x)]
    if len(named) == 1:
        return named[0], res[named[0]]
    t = catalog.topic(cat, s)
    if t:
        run = [r["rid"] for r in t.get("resources") or [] if catalog.is_runnable(r)]
        if len(run) == 1:
            return run[0], res[run[0]]
        named = run
    if named:
        raise LookupError(f"{s} is ambiguous; use one of: " + ", ".join(named[:8]))
    raise LookupError(f"{s}: not a catalog resource (give its URL)")


def slug(rid):
    s = re.sub(r"^https?://(www\.)?", "", rid)
    s = re.sub(r"^github\.com/", "", s)
    s = re.sub(r"/(tree|blob)/[^/]+/", "/", s)
    return re.sub(r"[^A-Za-z0-9._-]+", "__", s).strip("_.")[:150] or "item"


def _meta_sha(d, stop):
    """sha recorded in the nearest .garage.json at or above d (up to the mirror/quarantine root)."""
    d = Path(d)
    for p in [d, *d.parents]:
        f = p / ".garage.json"
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8")).get("sha")
            except (OSError, ValueError):
                return None
        if p in stop:
            break
    return None


def snapshot(rid, pin):
    """The folder holding this rid's pinned snapshot (quarantine first, then the mirror), or None."""
    if not pin or not pin.get("sha"):
        return None
    roots = [paths.quarantine(), paths.mirror()]
    cands = []
    try:
        from . import mirror
        p = mirror.local_path(rid)
        if p:
            cands.append(Path(p))
    except Exception:   # noqa: BLE001 - T2's module missing or failing: fall back to the documented layout
        pass
    owner, _, name = str(pin.get("repo", "")).partition("/")
    sub = str(pin.get("path") or "").strip("/")
    for root in roots:
        for o in dict.fromkeys([f"{owner}__{name}", f"{owner}__{name}".lower()]):
            base = root / o / pin["sha"][:12]
            cands.append(base / sub if sub else base)
    for c in cands:
        if c.is_dir() and _meta_sha(c, set(roots)) in (pin["sha"], None):
            return c.resolve()
    return None


# ---- running scanners ----------------------------------------------------------------------------------------------

def _tool(name, rel):
    p = SCANNERS / rel
    if p.is_file() and os.access(p, os.X_OK):
        return str(p)
    return shutil.which(name)


def versions():
    f = SCANNERS / "versions.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _version(name, exe, args, rx=r"(\d+\.\d+\.\d+)"):
    v = versions().get(name)
    if v:
        return v
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=30)
        m = re.search(rx, out.stdout + out.stderr)
        return m.group(1) if m else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


SAFE_ENV = {"HOME": "/tmp", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "NO_COLOR": "1", "TERM": "dumb",
            "COLUMNS": "200", "LITELLM_LOCAL_MODEL_COST_MAP": "True", "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false", "DO_NOT_TRACK": "1", "SKILLSPECTOR_LOG_LEVEL": "ERROR",
            "PYTHONDONTWRITEBYTECODE": "1"}


def sandboxed(argv, ro=(), rw=(), timeout=TIMEOUT):
    """Run a scanner: low priority, empty environment, and (with bubblewrap) a read-only root, no network, private
    /tmp, own pid namespace. -> CompletedProcess. The scanned files are only ever read."""
    nice = [x for x in ("nice", "ionice") if shutil.which(x)]
    pre = (["nice", "-n", "19"] if "nice" in nice else []) + (["ionice", "-c", "3"] if "ionice" in nice else [])
    bw = shutil.which("bwrap")
    if bw and os.environ.get("GARAGE_SCAN_SANDBOX", "1") != "0":
        cmd = [bw, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
        for p in ro:   # things under /tmp vanish behind the private /tmp: bind them back
            if str(p).startswith("/tmp/"):
                cmd += ["--ro-bind", str(p), str(p)]
        for p in rw:
            cmd += ["--bind", str(p), str(p)]
        cmd += ["--unshare-net", "--unshare-pid", "--unshare-ipc", "--die-with-parent", "--new-session",
                "--chdir", "/tmp", "--"]
        argv = cmd + ["/usr/bin/env", "-i"] + [f"{k}={v}" for k, v in SAFE_ENV.items()] + list(argv)
        return subprocess.run(pre + argv, capture_output=True, text=True, timeout=timeout, cwd="/")
    env = dict(SAFE_ENV, HOME=tempfile.gettempdir())
    return subprocess.run(pre + list(argv), capture_output=True, text=True, timeout=timeout, cwd="/", env=env)


def _venv_root(exe):
    p = Path(exe).resolve()
    return p.parent.parent if p.parent.name == "bin" else p.parent


def _res(tool, version, result, findings=0, details=None, note="", sandbox=None):
    return {"tool": tool, "version": version, "result": result, "findings": int(findings),
            "details": (details or [])[:60], "note": note[:300],
            "sandbox": sandbox if sandbox is not None else bool(shutil.which("bwrap")
                                                                  and os.environ.get("GARAGE_SCAN_SANDBOX") != "0")}


def skill_dirs(target):
    found = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
        if len(Path(root).relative_to(target).parts) > 5:
            dirs[:] = []
        if "SKILL.md" in files:
            found.append(Path(root))
    return found


def run_skillspector(target, out):
    exe = _tool("skillspector", "venv/bin/skillspector")
    if not exe:
        return _res("skillspector", "-", "skipped", note="not installed (infra/install.d/30-safety.sh)")
    exe = os.path.realpath(exe)
    ver = _version("skillspector", exe, ["--version"])
    dirs = skill_dirs(target) or [target]
    note = ""
    if len(dirs) > MAX_SKILL_DIRS:
        note = f"{len(dirs)} skills, first {MAX_SKILL_DIRS} scanned"
        dirs = dirs[:MAX_SKILL_DIRS]
    worst, details, n, errs = "pass", [], 0, []
    rank = {"pass": 0, "warn": 1, "fail": 2}
    for i, d in enumerate(dirs):
        rep = out / f"skillspector-{i}.json"
        try:
            p = sandboxed([exe, "scan", str(d), "--no-llm", "--format", "json", "-o", str(rep)],
                          ro=[target, _venv_root(exe)], rw=[out])
        except subprocess.TimeoutExpired:
            errs.append(f"{d.name}: timed out")
            continue
        try:
            r = json.loads(rep.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            errs.append(f"{d.name}: no report ({(p.stderr or p.stdout).strip()[-160:]})")
            continue
        ra = r.get("risk_assessment") or {}
        issues = r.get("issues") or []
        n += len(issues)
        sev = {str(x.get("severity", "")).upper() for x in issues} | {str(ra.get("severity", "")).upper()}
        res = "fail" if ra.get("recommendation") == "DO_NOT_INSTALL" or sev & {"CRITICAL", "HIGH"} else \
            "warn" if sev & {"MEDIUM"} else "pass"
        worst = max(worst, res, key=rank.get)
        rel = d.relative_to(target).as_posix() if d != target else "."
        for x in issues:
            loc = x.get("location") or {}
            details.append({"rule": x.get("id"), "severity": str(x.get("severity", "")).lower(),
                            "file": f"{rel}/{loc.get('file', '')}".removeprefix("./"), "line": loc.get("start_line"),
                            "text": str(x.get("pattern") or x.get("category") or "")[:60] + ": "
                            + str(x.get("finding") or x.get("explanation") or "")[:140]})
    if errs and len(errs) == len(dirs):
        return _res("skillspector", ver, "error", note="; ".join(errs)[:300])
    if errs:
        note = (note + "; " if note else "") + f"{len(errs)} folders not scanned: " + "; ".join(errs)[:200]
        worst = max(worst, "warn", key=rank.get)
    return _res("skillspector", ver, worst, n, _sort(details), note)


AG_SEV = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}


def run_aguara(target, out):
    exe = _tool("aguara", "bin/aguara")
    if not exe:
        return _res("aguara", "-", "skipped", note="not installed (infra/install.d/30-safety.sh)")
    ver = _version("aguara", exe, ["version"])
    try:
        p = sandboxed([exe, "scan", str(target), "--format", "json", "--no-update-check", "--no-color",
                       "--project-policy", "ignore"], ro=[target, Path(exe).parent])
    except subprocess.TimeoutExpired:
        return _res("aguara", ver, "error", note="timed out")
    try:
        r = json.loads(p.stdout)
    except ValueError:
        return _res("aguara", ver, "error", note=(p.stderr or p.stdout).strip()[-300:])
    fs = r.get("findings") or []
    top = max([int(f.get("severity", 0)) for f in fs] or [0])
    res = "fail" if top >= 3 else "warn" if top == 2 else "pass"
    details = [{"rule": f.get("rule_id"), "severity": AG_SEV.get(int(f.get("severity", 0)), "info"),
                "file": f.get("file_path"), "line": f.get("line"),
                "text": f"{f.get('rule_name', '')}: {str(f.get('matched_text', ''))[:120]}"} for f in fs]
    return _res("aguara", ver, res, len(fs), _sort(details))


def run_gitleaks(target, out):
    exe = _tool("gitleaks", "bin/gitleaks")
    if not exe:
        return _res("gitleaks", "-", "skipped", note="not installed")
    ver = versions().get("gitleaks") or _version("gitleaks", exe, ["version"])
    if ver == "unknown":
        ver = _deb_version("gitleaks")
    rep = out / "gitleaks.json"
    try:
        p = sandboxed([exe, "detect", "--no-git", "--source", str(target), "--report-format", "json",
                       "--report-path", str(rep), "--no-banner", "--redact", "--exit-code", "0",
                       "--log-level", "error"], ro=[target], rw=[out])
    except subprocess.TimeoutExpired:
        return _res("gitleaks", ver, "error", note="timed out")
    try:
        fs = json.loads(rep.read_text(encoding="utf-8") or "[]")
    except (OSError, ValueError):
        return _res("gitleaks", ver, "error", note=(p.stderr or p.stdout).strip()[-300:])
    details = [{"rule": f.get("RuleID"), "severity": "high", "file": f.get("File", "").replace(str(target) + "/", ""),
                "line": f.get("StartLine"), "text": str(f.get("Description", ""))[:120]} for f in fs]
    return _res("gitleaks", ver, "fail" if fs else "pass", len(fs), details)


def _deb_version(pkg):
    try:
        out = subprocess.run(["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# MCP tool descriptions, read from source without running the server.
TOOL_PATTERNS = [
    re.compile(r"""\.(?:tool|registerTool)\(\s*(["'`])(?P<name>[\w.-]{1,64})\1\s*,\s*(?:\{[^{}]{0,400}?description\s*:\s*)?"""
               r"""(["'`])(?P<desc>(?:\\.|(?!\3).){8,4000}?)\3""", re.S),
    re.compile(r"""name\s*[:=]\s*(["'])(?P<name>[\w.-]{1,64})\1\s*,\s*(?:title\s*[:=]\s*(["']).*?\3\s*,\s*)?"""
               r"""description\s*[:=]\s*(["'`])(?P<desc>(?:\\.|(?!\4).){8,4000}?)\4""", re.S),
    re.compile(r"""\bTool\(\s*name\s*=\s*(?P<name>[\w.]{1,80}|"[\w.-]{1,64}")\s*,\s*description\s*=\s*(?P<q>\"\"\"|"|')"""
               r"""(?P<desc>(?:\\.|(?!(?P=q)).){8,4000}?)(?P=q)""", re.S),
    re.compile(r"""\.tool\(\s*(?:name\s*=\s*(?P<name>["']?[\w.-]{1,80}["']?)\s*,\s*)?(?:title\s*=\s*(["']).*?\2\s*,\s*)?"""
               r"""description\s*=\s*(["'])(?P<desc>(?:\\.|(?!\3).){8,4000}?)\3""", re.S),
    re.compile(r"""NewTool\(\s*"(?P<name>[\w.-]{1,64})"\s*,\s*mcp\.WithDescription\(\s*(["`])(?P<desc>(?:\\.|(?!\2).){8,4000}?)\2""",
               re.S),
    re.compile(r"""@\w+\.tool\([^)]*\)\s*\n\s*(?:async\s+)?def\s+(?P<name>\w+)\s*\([^)]*\)[^:]*:\s*\n\s*(?P<q>\"\"\"|''')"""
               r"""(?P<desc>.{8,4000}?)(?P=q)""", re.S),
]
CODE_EXT = {".py", ".ts", ".js", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".tsx"}


def extract_tools(target, limit=300):
    tools, seen = [], set()
    for f in _walk(target):
        if f.suffix not in CODE_EXT or f.stat().st_size > MAX_READ or "test" in f.as_posix().lower():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in TOOL_PATTERNS:
            for m in pat.finditer(text):
                name = (m.group("name") or "tool").strip("\"'").removesuffix(".value").split(".")[-1]
                desc = " ".join(m.group("desc").split())
                if (name, desc[:80]) in seen:
                    continue
                seen.add((name, desc[:80]))
                tools.append({"name": name, "description": desc,
                              "inputSchema": {"type": "object", "properties": {}}})
                if len(tools) >= limit:
                    return tools
    return tools


def run_mcp_scanner(target, out, kind):
    exe = _tool("mcp-scanner", "venv/bin/mcp-scanner")
    if kind != "mcp":
        return _res("mcp-scanner", "-", "skipped", note="not an MCP server")
    if not exe:
        return _res("mcp-scanner", "-", "skipped", note="not installed (infra/install.d/30-safety.sh)")
    exe = os.path.realpath(exe)
    ver = versions().get("mcp-scanner", "unknown")
    tools = extract_tools(target)
    if not tools:
        return _res("mcp-scanner", ver, "skipped", note="no tool descriptions found in the source (read them by hand)")
    tf = out / "tools.json"
    tf.write_text(json.dumps({"tools": tools}), encoding="utf-8")
    try:
        p = sandboxed([exe, "--analyzers", "yara", "--format", "raw", "static", "--tools", str(tf)],
                      ro=[_venv_root(exe)], rw=[out])
    except subprocess.TimeoutExpired:
        return _res("mcp-scanner", ver, "error", note="timed out")
    txt = p.stdout[p.stdout.find("{"):] if "{" in p.stdout else ""
    try:
        r = json.loads(txt)
    except ValueError:
        return _res("mcp-scanner", ver, "error", note=(p.stderr or p.stdout).strip()[-300:])
    details, worst = [], "pass"
    for s in r.get("scan_results") or []:
        y = (s.get("findings") or {}).get("yara_analyzer") or {}
        sev = str(y.get("severity", "SAFE")).upper()
        if s.get("is_safe", True) and sev in ("SAFE", ""):
            continue
        worst = "fail" if sev in ("HIGH", "CRITICAL") else ("warn" if worst == "pass" else worst)
        details.append({"rule": ",".join(y.get("threat_names") or [])[:60], "severity": sev.lower(),
                        "file": "tool " + str(s.get("tool_name")), "line": None,
                        "text": str(y.get("threat_summary", ""))[:160]})
    return _res("mcp-scanner", ver, worst, len(details), details, f"{len(tools)} tool descriptions from source")


# ---- our own checks ------------------------------------------------------------------------------------------------

INSTR_NAMES = {"skill.md", "claude.md", "agents.md", "gemini.md", ".cursorrules", "copilot-instructions.md"}
INSTR_EXT = {".md", ".mdc", ".mdx", ".txt", ".prompt", ".rst"}
EXEC_EXT = {".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".cjs", ".ts", ".go", ".rb", ".pl", ".ps1", ".php", ".rs"}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "uv.lock", "poetry.lock",
             "pdm.lock", "go.sum", "cargo.lock", "gemfile.lock", "composer.lock", "pipfile.lock", "requirements.lock"}
ARCHIVE_EXT = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".jar", ".whl", ".xz", ".bz2", ".zst", ".egg", ".apk",
               ".deb", ".rpm", ".dmg", ".pkg", ".crx", ".vsix", ".nupkg"}
COMPILED_EXT = {".pyc", ".pyo", ".class", ".so", ".dll", ".dylib", ".exe", ".bin", ".o", ".a", ".node", ".wasm",
                ".elf", ".msi", ".scr", ".com"}
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".bmp", ".woff", ".woff2", ".ttf", ".otf",
             ".eot", ".pdf", ".mp4", ".mp3", ".wav", ".webm", ".mov", ".avif", ".icns", ".psd"}
SUPPRESS_FILES = {".gitleaks.toml", ".gitleaksignore", ".skillspector-baseline.yaml", ".skillspector-baseline.yml",
                  ".aguara.yml", ".aguara.yaml", ".aguaraignore", "aguara.yml", ".semgrepignore", ".trivyignore"}
MAGIC_EXEC = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa")

HIDDEN_HIGH = re.compile("[‪-‮⁦-⁩\U000e0000-\U000e007f]")
ZERO_WIDTH = re.compile("[​‌‍⁠⁡⁢⁣⁤᠎﻿]")
B64 = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/]{200,}={0,2}(?![A-Za-z0-9+/=])")
HEX = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{200,}(?![0-9A-Fa-f])")
OVERRIDE_HIGH = re.compile(
    r"ignore\s+(all\s+|any\s+)?(of\s+)?(the\s+|your\s+)?(previous|prior|above|earlier|preceding|system)\s+"
    r"(instructions|prompts?|rules|directions|messages)"
    r"|disregard\s+(all\s+|any\s+)?(the\s+|your\s+)?(previous|prior|above|earlier|system)\s+(instructions|prompts?|rules)"
    r"|forget\s+(all\s+|everything\s+)?(your\s+|the\s+)?(previous\s+|prior\s+)?(instructions|rules|guidelines)"
    r"|(do\s+not|don'?t|never)\s+(tell|inform|mention\s+(this\s+)?to|notify|alert|reveal\s+(this\s+)?to|show)\s+"
    r"(this\s+)?(to\s+)?the\s+user"
    r"|without\s+(telling|informing|asking|notifying|alerting)\s+the\s+user"
    r"|(override|bypass|ignore)\s+(the\s+|your\s+|any\s+)?(system\s+prompt|safety\s+(rules|guidelines)|guardrails"
    r"|permission\s+(rules|prompts|checks))"
    r"|new\s+system\s+prompt\s*:", re.I)
OVERRIDE_MED = re.compile(r"\byou\s+are\s+now\s+(a|an|in|the|no\s+longer)\b|\bdeveloper\s+mode\s+(enabled|on)\b"
                          r"|<\s*/?\s*(IMPORTANT|SYSTEM|system-prompt|hidden)\s*>|\bjailbr(eak|oken)\b", re.I)
PIPE_SH = re.compile(
    r"\b(curl|wget|fetch|iwr|irm|invoke-webrequest|invoke-restmethod)\b[^\n|;&]{0,300}\|\s*"
    r"(sudo\s+(-\S+\s+)*)?(env\s+\S+\s+)?((ba|z|da|k|fi|c)?sh|python[23]?|node|perl|ruby|php|iex|invoke-expression)\b"
    r"|\b(ba|z)?sh\s+(-c\s+)?[\"']?\$\(\s*(curl|wget)\b|<\(\s*(curl|wget)\b"
    r"|\beval\s+[\"']?\$\(\s*(curl|wget)\b", re.I)
FETCH_INSTR = re.compile(
    r"(fetch|download|curl|wget|webfetch|retrieve|load|read|get|pull|follow)\b[^\n]{0,80}https?://[^\s)\"'>]+[^\n]{0,80}"
    r"\b(instructions?|prompts?|rules|commands|steps|directives|skill\s+file|latest\s+version\s+of\s+(this|these))\b"
    r"|\b(instructions?|prompts?|rules|directives)\b[^\n]{0,60}\b(from|at)\s+https?://"
    r"|(fetch|download|webfetch|retrieve|load)\b[^\n]{0,40}\b(instructions?|prompts?|rules|directives)\b[^\n]{0,60}"
    r"https?://", re.I)
PASTE_HOST = re.compile(r"https?://(www\.)?(pastebin\.com|paste\.\w+|[\w.-]*hastebin|ghostbin|transfer\.sh|0x0\.st|"
                        r"termbin\.com|rentry\.(co|org)|controlc\.com|gist\.githubusercontent\.com|ngrok\.(io|app)|"
                        r"[\w-]+\.trycloudflare\.com|webhook\.site|requestbin|pipedream\.net|interact\.sh|oast\.)", re.I)
PERSIST = re.compile(
    r"\bcrontab\b|/etc/cron|@reboot\b|/etc/systemd/|systemctl\s+(--user\s+)?enable\b|\.config/systemd/user|"
    r"Library/Launch(Agents|Daemons)|/etc/rc\.local|/etc/profile\.d|/etc/init\.d/|"
    r"(>>?|\btee(\s+-a)?)\s*[\"']?(~|\$HOME|\$\{HOME\})?/?[\w./-]*\.(bashrc|zshrc|profile|bash_profile|zprofile|zshenv)\b|"
    r"(>>?|\btee(\s+-a)?|write_?(text|file)?\(|appendFile)\s*[^\n]{0,60}(CLAUDE\.md|AGENTS\.md|MEMORY\.md|\.claude/|"
    r"\.cursorrules|\.codex/|\.gemini/)|authorized_keys", re.I)
SENSITIVE = re.compile(
    r"~/\.ssh\b|\.ssh/(id_|authorized_keys|config)|id_(rsa|ed25519|ecdsa)\b|\.aws/credentials|\.config/gcloud|"
    r"\.azure/|\.kube/config|\.docker/config\.json|\.netrc\b|\.npmrc\b|\.pypirc\b|\.git-credentials|\.gnupg|"
    r"/etc/shadow|wallet\.dat|keystore|metamask|phantom|seed\s+phrase|mnemonic|Login\s+Data|Local\s+State|"
    r"Cookies\.sqlite|key4\.db|logins\.json|\.mozilla/firefox|Google/Chrome|BraveSoftware|Keychains?\b|"
    r"\.claude/\.credentials|\.claude\.json\b", re.I)
EXFIL_NEAR = re.compile(r"\b(curl|wget|nc|ncat|requests\.(post|put)|fetch\(|axios\.post|http\.request|urlopen|"
                        r"scp|rsync|ftp)\b", re.I)
INSTALL_SCRIPTS = ("preinstall", "install", "postinstall", "prepare", "prepublish", "preuninstall", "postuninstall")
SHELL_HINT = re.compile(r"\b(subprocess|child_process|os\.system|os\.popen|execSync|spawnSync|exec\.Command|"
                        r"Runtime\.getRuntime|shell=True|Popen)\b|```(bash|sh|shell|zsh|console)\b", re.I)
NET_HINT = re.compile(r"\b(requests\.(get|post)|httpx|urllib\.request|urlopen|aiohttp|axios|node-fetch|"
                      r"http\.Get|net/http|reqwest|WebFetch|WebSearch)\b|\bfetch\(|\b(curl|wget)\s", re.I)
FILES_HINT = re.compile(r"open\([^)]*[\"'][wa]b?\+?[\"']|\bwrite_text\(|\bwriteFile(Sync)?\(|fs\.(write|rm|unlink)|"
                        r"os\.(remove|unlink|rename)|shutil\.(rmtree|move|copy)|\brm\s+-rf?\b", re.I)
SECRET_HINT = re.compile(r"(os\.environ|getenv|process\.env|os\.Getenv|env::var)[^\n]{0,40}"
                         r"(KEY|TOKEN|SECRET|PASSWORD|PASS|CREDENTIAL)", re.I)


def _walk(target):
    """Every regular file of the item (no .git); symlinks are not followed."""
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d != ".git"]
        for n in files:
            yield Path(root) / n


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _line_text(text, pos):
    end = text.find("\n", pos)
    return text[text.rfind("\n", 0, pos) + 1:end if end >= 0 else len(text)]


def _frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        import yaml
        d = yaml.safe_load(text[3:end])
        return d if isinstance(d, dict) else {}
    except Exception:   # noqa: BLE001 - a broken frontmatter is reported elsewhere, not fatal
        return {}


def _emoji_zwj(text, pos):
    a, b = text[pos - 1:pos], text[pos + 1:pos + 2]
    return text[pos] == "‍" and a and b and (ord(a) > 0x2100 or ord(b) > 0x2100)


def _decoded_hits(blob):
    try:
        raw = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False)
    except (binascii.Error, ValueError):
        return None
    txt = raw.decode("latin-1")
    printable = sum(32 <= ord(c) < 127 or c in "\n\r\t" for c in txt) / max(1, len(txt))
    m = re.search(r"(curl|wget|/bin/(ba)?sh|bash\s+-|eval\(|exec\(|powershell|python\s+-c|import\s+os|"
                  r"subprocess|https?://|nc\s+-e|\bchmod\s+\+x)", txt, re.I)
    return (m.group(0) if m else None), printable


def own_checks(target, kind=""):
    """Our checks from research/system-design.md section 4. -> scanner result + capabilities + stats."""
    target = Path(target)
    fs = []
    seen = {}

    def add(rule, sev, f, line, text):
        k = (rule, f)
        seen[k] = seen.get(k, 0) + 1
        if seen[k] <= 3:
            fs.append({"rule": rule, "severity": sev, "file": f, "line": line, "text": str(text)[:160]})

    can = {"shell": False, "network": False, "files": False, "secrets": False}
    total, nfiles, deps, locks, media = 0, 0, 0, set(), 0
    for f in _walk(target):
        rel = f.relative_to(target).as_posix()
        name, ext = f.name.lower(), f.suffix.lower()
        nfiles += 1
        if f.is_symlink():
            dest = os.path.realpath(f)
            if not (dest + "/").startswith(str(target.resolve()) + "/"):
                add("symlink-escape", "high", rel, None, f"symlink out of the item -> {os.readlink(f)}")
            continue
        try:
            size = f.stat().st_size
        except OSError:
            continue
        total += size
        if name in LOCKFILES:
            locks.add(name)
        if name in SUPPRESS_FILES:
            add("scanner-suppression", "high", rel, None, "ships a scanner config/ignore file that could hide findings")
        if "/node_modules/" in f"/{rel}" and name == "package.json":
            add("vendored-deps", "medium", rel, None, "ships node_modules (unreviewable third-party code)")
        if name == ".mcp.json" or rel.endswith(("hooks/hooks.json", ".claude/settings.json",
                                                 ".claude/settings.local.json")) or \
                (name in ("settings.json", "settings.local.json") and "/.claude/" in f"/{rel}"):
            sev = "medium" if kind in ("plugin", "mcp") and name != "settings.local.json" else "high"
            add("agent-config-inside", sev, rel, None, "hooks/.mcp.json/settings inside the item: they run "
                "without a prompt under claude -p; read every command")
        if ext in COMPILED_EXT:
            add("compiled-binary", "high", rel, None, f"compiled/binary code ({ext}) can't be reviewed")
            continue
        if ext in ARCHIVE_EXT:
            add("archive", "medium", rel, None, f"archive ({ext}): contents not scanned")
            continue
        if ext == ".pth":
            add("install-hook", "high", rel, None, ".pth file: runs code at every Python start")
        try:
            with open(f, "rb") as fh:
                head = fh.read(MAX_READ)
        except OSError:
            continue
        if head.startswith(MAGIC_EXEC) and ext not in MEDIA_EXT:
            add("compiled-binary", "high", rel, None, "executable binary")
            continue
        if b"\x00" in head[:8192]:
            if ext in MEDIA_EXT:
                media += 1
            else:
                add("binary-file", "medium", rel, None, "binary file of unknown type")
            continue
        if size > TEXT_BIG:
            add("oversized-file", "medium", rel, None, f"text file of {size // 1000} kB (padding hides payloads)")
        text = head.decode("utf-8", errors="replace")
        is_instr = name in INSTR_NAMES or ext in INSTR_EXT
        is_exec = ext in EXEC_EXT or text.startswith("#!")
        if ext in (".js", ".mjs", ".cjs", ".css") and (name.endswith((".min.js", ".min.css")) or
                                                       any(len(ln) > 5000 for ln in text.splitlines()[:200])):
            add("minified", "medium", rel, None, "minified/bundled code: review the source it was built from")
        for m in HIDDEN_HIGH.finditer(text):
            c = m.group()
            if 0xE0000 <= ord(c) <= 0xE007F:   # a run of tag characters spells hidden ASCII text
                run = re.match("[\U000e0000-\U000e007f]+", text[m.start():]).group()
                if m.start() and 0xE0000 <= ord(text[m.start() - 1]) <= 0xE007F:
                    continue
                add("hidden-unicode", "high", rel, _line(text, m.start()),
                    "hidden tag-character text: " + repr("".join(chr(ord(x) - 0xE0000) for x in run))[:80])
            else:
                add("hidden-unicode", "high", rel, _line(text, m.start()), f"bidi control character U+{ord(c):04X}")
        for m in ZERO_WIDTH.finditer(text):
            if (m.group() == "﻿" and m.start() == 0) or _emoji_zwj(text, m.start()):
                continue
            add("hidden-unicode", "high", rel, _line(text, m.start()), f"zero-width character U+{ord(m.group()):04X}")
        if name not in LOCKFILES and ext not in (".svg", ".map", ".lock", ".sum"):
            for m in B64.finditer(text):
                blob = m.group()
                if not (re.search(r"[0-9]", blob) and re.search(r"[A-Z]", blob) and re.search(r"[a-z]", blob)):
                    continue
                pre = text[max(0, m.start() - 40):m.start()]
                hit = _decoded_hits(blob)
                if hit and hit[0]:
                    add("encoded-payload", "high", rel, _line(text, m.start()),
                        f"base64 blob ({len(blob)} chars) decodes to text with '{hit[0]}'")
                elif "base64," in pre:
                    add("encoded-blob", "low", rel, _line(text, m.start()), f"data URI ({len(blob)} chars)")
                else:
                    add("encoded-blob", "medium", rel, _line(text, m.start()), f"base64-like blob of {len(blob)} chars")
            for m in HEX.finditer(text):
                add("encoded-blob", "medium", rel, _line(text, m.start()), f"hex blob of {len(m.group())} chars")
        for m in OVERRIDE_HIGH.finditer(text):
            add("override-phrase", "high", rel, _line(text, m.start()), m.group())
        for m in OVERRIDE_MED.finditer(text):
            add("override-phrase", "medium", rel, _line(text, m.start()), m.group())
        for m in PIPE_SH.finditer(text):
            add("curl-pipe-shell", "high", rel, _line(text, m.start()), m.group())
        if is_instr:
            for m in FETCH_INSTR.finditer(text):
                add("runtime-instructions", "high", rel, _line(text, m.start()), m.group())
            for m in PASTE_HOST.finditer(text):
                add("paste-host", "medium", rel, _line(text, m.start()), m.group())
        elif is_exec:
            for m in PASTE_HOST.finditer(text):
                add("paste-host", "high", rel, _line(text, m.start()), m.group())
        for m in PERSIST.finditer(text):
            add("persistence", "high" if is_exec or name == "skill.md" else "medium", rel, _line(text, m.start()),
                m.group())
        for m in SENSITIVE.finditer(text):
            ln = _line_text(text, m.start())
            if EXFIL_NEAR.search(ln):
                add("exfiltration", "high", rel, _line(text, m.start()), ln.strip()[:160])
            else:
                add("sensitive-path", "medium" if is_exec or name == "skill.md" else "low", rel,
                    _line(text, m.start()), m.group())
        if name == "package.json":
            try:
                pj = json.loads(text)
            except ValueError:
                pj = {}
            for k in INSTALL_SCRIPTS:
                v = (pj.get("scripts") or {}).get(k) if isinstance(pj.get("scripts"), dict) else None
                if v:
                    add("install-hook", "medium", rel, None, f"npm {k}: {v}")
            deps += len(pj.get("dependencies") or {}) + len(pj.get("optionalDependencies") or {})
        if name == "setup.py":
            add("install-hook", "medium", rel, None, "setup.py runs code at install time")
        if name.startswith("requirements") and ext == ".txt":
            deps += sum(1 for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", "-")))
        if name == "pyproject.toml":
            m = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)\]", text)
            deps += len(re.findall(r"[\"'][^\"']+[\"']", m.group(1))) if m else 0
        if name == "go.mod":
            deps += len(re.findall(r"(?m)^\s+[\w.-]+\.[\w./-]+\s+v\d", text))
        if name in ("skill.md",) or (ext == ".md" and re.search(r"(^|/)(agents|commands)/", rel)):
            fm = _frontmatter(text)
            tools = fm.get("allowed-tools", fm.get("tools"))
            if isinstance(tools, str):
                tools = [t.strip() for t in re.split(r",\s*|\s+(?=[A-Z])", tools) if t.strip()]
            for t in tools or []:
                t = str(t).strip()
                if t in ("*", "Bash", "Bash(*)", "Bash(*:*)", "Bash(**)") or t.startswith("Bash(sudo"):
                    add("allowed-tools", "medium", rel, None, f"blanket shell in allowed-tools: {t}")
                if t.startswith("Bash"):
                    can["shell"] = True
                if t.startswith(("WebFetch", "WebSearch")):
                    can["network"] = True
                if t.startswith(("Write", "Edit", "MultiEdit", "NotebookEdit")):
                    can["files"] = True
        if is_exec or is_instr:
            can["shell"] |= bool(SHELL_HINT.search(text)) or (is_exec and ext in (".sh", ".bash", ".zsh"))
            can["network"] |= bool(NET_HINT.search(text))
            can["files"] |= bool(FILES_HINT.search(text))
            can["secrets"] |= bool(SECRET_HINT.search(text)) or any(x["rule"] in ("sensitive-path", "exfiltration")
                                                                    and x["file"] == rel for x in fs)
    if total > ITEM_BIG:
        add("oversized-item", "medium", ".", None, f"item is {total // 1_000_000} MB (over 10 MB)")
    if nfiles > 5000:
        add("many-files", "low", ".", None, f"{nfiles} files")
    if deps and not locks:
        add("no-lockfile", "low", ".", None, f"{deps} dependencies and no lockfile: versions float")
    if kind == "template":
        for x in fs:
            if x["rule"] == "agent-config-inside":
                x["severity"] = "high"   # garage templates never ship .mcp.json or hooks
    sev = {x["severity"] for x in fs}
    result = "fail" if "high" in sev else "warn" if "medium" in sev else "pass"
    r = _res("garage-checks", CHECKS_VERSION, result, len(fs), _sort(fs), sandbox=False)
    r["capabilities"] = can
    r["stats"] = {"files": nfiles, "bytes": total, "media": media, "dependencies": deps, "lockfiles": sorted(locks)}
    return r


SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _sort(details):
    return sorted(details, key=lambda d: SEV_RANK.get(str(d.get("severity")), 5))


# ---- the scan ------------------------------------------------------------------------------------------------------

def guess_kind(target, res=None):
    if res:
        if res.get("use") in ("mcp",) or res.get("kind") == "mcp":
            return "mcp"
        for k in ("skill", "plugin", "template"):
            if res.get("use") == k or res.get("kind") == k:
                return k
        if res.get("use") == "vendor" or res.get("kind") == "snippet":
            return "vendor"
    t = Path(target)
    if (t / ".claude-plugin" / "plugin.json").is_file():
        return "plugin"
    if (t / "SKILL.md").is_file():
        return "skill"
    for f in ("package.json", "pyproject.toml", "go.mod"):
        p = t / f
        if p.is_file() and re.search(r"modelcontextprotocol|\bmcp\b|fastmcp|mcp-go", p.read_text(errors="replace")):
            return "mcp"
    return "vendor"


def scan_dir(target, kind="", rid=None, sha=None):
    target = Path(target).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"{target}: not a folder")
    kind = kind or guess_kind(target)
    with tempfile.TemporaryDirectory(prefix="garage-scan-") as tmp:
        out = Path(tmp)
        results = [run_skillspector(target, out), run_aguara(target, out), run_gitleaks(target, out),
                   run_mcp_scanner(target, out, kind)]
    own = own_checks(target, kind)
    results.append({k: v for k, v in own.items() if k not in ("capabilities", "stats")})
    worst = "fail" if any(r["result"] == "fail" for r in results) else \
        "warn" if any(r["result"] in ("warn", "error") for r in results) else "pass"
    missing = [r["tool"] for r in results if r["tool"] in REQUIRED and r["result"] in ("skipped", "error")]
    return {"rid": rid, "sha": sha, "target": str(target), "kind": kind,
            "date": dt.date.today().isoformat(), "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "result": worst, "complete": not missing, "missing": missing, "scanners": results,
            "capabilities": own["capabilities"], "stats": own["stats"]}


def report_file(rid, sha):
    return paths.state() / "scans" / slug(rid) / f"{sha[:12]}.json"


def last_report(rid, sha):
    f = report_file(rid, sha)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def scan_item(ident, store=True):
    """Scan the pinned snapshot of a catalog item. -> report (also stored under state/scans/)."""
    rid, res = resolve(ident)
    from . import pins
    pin = pins.get(rid)
    if not pin:
        raise LookupError(f"{rid}: not pinned in lock/pins.yaml (garage pin first)")
    d = snapshot(rid, pin)
    if not d:
        raise LookupError(f"{rid}: no snapshot of {pin['sha'][:12]} in {paths.quarantine()} or {paths.mirror()} "
                          "(garage mirror first)")
    rep = scan_dir(d, guess_kind(d, res), rid, pin["sha"])
    rep["name"] = (res or {}).get("name")
    if store:
        f = report_file(rid, pin["sha"])
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
            rep["report"] = str(f)
        except OSError as e:
            rep["report"] = f"not stored ({e})"
    return rep


def summary_lines(rep, top=4):
    out = [f"scan {rep.get('rid') or rep['target']} @ {str(rep.get('sha') or '')[:12]}  kind {rep['kind']}  "
           f"-> {rep['result'].upper()}" + ("" if rep["complete"] else f"  (incomplete: {', '.join(rep['missing'])})")]
    for r in rep["scanners"]:
        out.append(f"  {r['tool']:13} {r['version']:>10}  {r['result']:7} {r['findings']:4} findings"
                   + (f"  ({r['note']})" if r.get("note") else "") + ("" if r.get("sandbox") or r["tool"] ==
                                                                        "garage-checks" else "  [no sandbox]"))
        for d in r["details"][:top]:
            if r["result"] in ("fail", "warn"):
                out.append(f"      {d.get('severity', ''):8} {d.get('rule')}  {d.get('file')}"
                           + (f":{d['line']}" if d.get("line") else "") + f"  {d.get('text', '')[:100]}")
    c = rep["capabilities"]
    out.append("  can: " + ", ".join(k for k, v in c.items() if v) if any(c.values()) else "  can: nothing found")
    return out


def registry_scans(rep):
    """The short form kept in trust/registry.yaml."""
    return [{"tool": r["tool"], "version": str(r["version"]), "date": rep["date"], "result": r["result"],
             "findings": r["findings"]} for r in rep["scanners"]]


def health():
    out = []
    for name, rel in (("skillspector", "venv/bin/skillspector"), ("aguara", "bin/aguara"),
                      ("gitleaks", "bin/gitleaks"), ("mcp-scanner", "venv/bin/mcp-scanner")):
        exe = _tool(name, rel)
        out.append(("PASS" if exe else "WAIT", f"scanner {name}: {exe or 'not installed (30-safety.sh)'}"))
    out.append(("PASS" if shutil.which("bwrap") else "WAIT", "scanner sandbox: bubblewrap"
                + ("" if shutil.which("bwrap") else " missing (scanners run unboxed)")))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garage scan", description=__doc__.split("\n")[0])
    ap.add_argument("id", nargs="?", help="catalog resource: URL/rid, owner/repo[/path], name, or topic id")
    ap.add_argument("--path", help="scan this folder instead of a catalog item (nothing stored)")
    ap.add_argument("--kind", default="", choices=["", "skill", "mcp", "plugin", "template", "vendor"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="only the first line")
    a = ap.parse_args(argv)
    try:
        if a.path:
            rep = scan_dir(a.path, a.kind)
        elif a.id:
            rep = scan_item(a.id)
        else:
            ap.error("give an ID or --path")
    except (LookupError, FileNotFoundError) as e:
        print(f"garage scan: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(rep, indent=1, ensure_ascii=False))
    else:
        lines = summary_lines(rep)
        print("\n".join(lines[:1] if a.quiet else lines))
        if rep.get("report"):
            print(f"  report: {rep['report']}")
    return 1 if rep["result"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
