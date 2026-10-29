"""T3 tests: the MCP server (results <= 3 KB, trust rules, grep confinement, stdio + HTTP transports), the plugin
(structure, `claude plugin validate`), and the server's managed settings (hook kept, drop-in valid).

Run: python3 -I -m unittest discover -s tests/t3 -v   (the transport tests need the `mcp` package, e.g.
/opt/garage/venv/bin/python; without it they are skipped). Other tracks' modules are mocked here.
"""
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
PLUGIN = REPO / "plugins" / "garage"
LIMIT = 3000
TRUST_LINES = [
    "## Trust",
    "- `quarantine`: read only (`garage show`, `garage grep`); never add, install or run it.",
    "- `reviewed`: OK in interactive sessions; tell the user it is \"reviewed, not yet trusted\".",
    "- `trusted`: OK in unattended runs too.",
    "- `GARAGE_UNATTENDED=1` (scheduled jobs, the assistant): use `trusted` items only.",
]

try:
    import mcp  # noqa: F401
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False


def big_text(n):
    return ("lorem ipsum dolor sit amet " * (n // 27 + 1))[:n]


RES = {
    "q": {"rid": "https://github.com/o/quarantined-skill", "name": "q-skill", "url": "https://github.com/o/quarantined-skill",
          "kind": "skill", "use": "skill", "license": "MIT", "topics": ["t.a.b"]},
    "r": {"rid": "https://github.com/o/reviewed-mcp", "name": "r-mcp", "url": "https://github.com/o/reviewed-mcp",
          "kind": "mcp", "use": "mcp", "license": "Apache-2.0", "topics": ["t.a.b"]},
    "t": {"rid": "https://github.com/o/trusted-tpl", "name": "t-tpl", "url": "https://github.com/o/trusted-tpl",
          "kind": "template", "use": "template", "license": "GPL-3.0", "topics": ["t.a.b"]},
    "p": {"rid": "https://www.npmjs.com/package/leftpad", "name": "leftpad", "url": "https://www.npmjs.com/package/leftpad",
          "kind": "repo", "use": "install", "license": "none", "topics": ["t.a.b"]},
}
TIERS = {RES["q"]["rid"]: "quarantine", RES["r"]["rid"]: "reviewed", RES["t"]["rid"]: "trusted"}


def fake_modules(mirror_root=None):
    """garage.search / trust / mirror stand-ins with the frozen contract's shapes."""
    search = types.ModuleType("garage.search")
    catalog = types.ModuleType("garage.catalog")
    trust = types.ModuleType("garage.trust")
    mirror = types.ModuleType("garage.mirror")
    catalog.is_runnable = lambda res: res.get("use") in {"skill", "mcp", "plugin", "template", "vendor"}

    def trust_of(res):
        return TIERS.get(res["rid"], "n/a") if catalog.is_runnable(res) else "n/a"

    def brief(res):
        return {"name": res["name"], "url": res["url"], "kind": res["kind"], "use": res["use"], "license": res["license"],
                "trust": trust_of(res), "install": search.install_line(res), "local_path": None}

    def do_search(q, kind=None, use=None, slice=None, trust=None, license=None, limit=5):
        out = []
        for i in range(limit):
            res = list(RES.values())[i % len(RES)]
            out.append({"id": f"t.area.topic-{i}", "title": f"Topic {i} " + big_text(150), "why": big_text(400),
                        "score": 10.0 - i, "best": brief(res)})
        return out

    def resolve(ref):
        if ref == "t.a.b":
            return {"id": "t.a.b", "title": "T"}, list(RES.values())
        for r in RES.values():
            if ref in (r["rid"], r["name"]):
                return None, [r]
        return None, []

    def show(ref):
        t, rs = resolve(ref)
        if not t and not rs:
            return {}
        if t:
            return {"id": "t.a.b", "title": "T", "why": big_text(2000), "practices": [big_text(300)] * 5,
                    "resources": [dict(r, trust=trust_of(r), note=big_text(500)) for r in rs] * 4, "see_also": []}
        return dict(rs[0], trust=trust_of(rs[0]))

    def install_line(res):
        if res["use"] == "install":
            return "npm install leftpad"
        return f"garage add {res['rid']}"

    search.search, search.show, search.resolve, search.trust_of = do_search, show, resolve, trust_of
    search.install_line = install_line
    search.recipe = lambda res: {"pin": {"sha": "a" * 40, "pinned": "2026-10-29"}}

    def allowed(rid, unattended):
        tr = TIERS.get(rid, "quarantine")
        if tr == "trusted":
            return True, "trusted"
        if tr == "reviewed" and not unattended:
            return True, "reviewed"
        return False, tr

    trust.tier = lambda rid: TIERS.get(rid, "quarantine")
    trust.allowed = allowed
    mirror.local_path = lambda rid: mirror_root if mirror_root and rid == RES["q"]["rid"] else None
    return {"garage.search": search, "garage.catalog": catalog, "garage.trust": trust, "garage.mirror": mirror}


class Fit(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module("garage.mcp_server")

    def test_small_unchanged(self):
        obj = {"a": 1, "b": "x"}
        self.assertEqual(json.loads(self.m.fit(obj)), obj)

    def test_big_fits_and_says_so(self):
        for obj in ({"results": [{"t": big_text(900), "l": [big_text(300)] * 20}] * 30},
                    [big_text(100000)], {"deep": {"deeper": [[big_text(5000)] * 5] * 5}}, {"s": "é" * 9000}):
            text = self.m.fit(obj)
            self.assertLessEqual(len(text.encode()), LIMIT)
            self.assertTrue(json.loads(text)["truncated"])


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        root = Path(self.tmp) / "snap"
        (root / "src").mkdir(parents=True)
        (root / "src" / "a.py").write_text("def handler():\n    return 'needle here'\n")
        (root / "README.md").write_text("needle in the readme\n")
        (root / "bin.dat").write_bytes(b"\0needle\0")
        os.symlink("/etc/passwd", root / "link")
        self.root = str(root)
        self.saved = {k: sys.modules.get(k) for k in fake_modules()}
        sys.modules.update(fake_modules(self.root))
        import garage
        garage._missing.clear()
        self.m = importlib.import_module("garage.mcp_server")
        os.environ.pop("GARAGE_UNATTENDED", None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        shutil.rmtree(self.tmp)
        os.environ.pop("GARAGE_UNATTENDED", None)

    def j(self, text):
        self.assertLessEqual(len(text.encode()), LIMIT, text[:200])
        return json.loads(text)

    def test_search_show_fit(self):
        for limit in (1, 5, 10, 50):
            d = self.j(self.m.tool_search("anything", limit=limit))
            self.assertTrue(d["results"])
            self.assertIn("trust", d["results"][0]["best"])
        d = self.j(self.m.tool_show("t.a.b"))
        self.assertTrue(d.get("truncated"))
        d = self.j(self.m.tool_show(RES["q"]["rid"]))
        self.assertEqual(next(iter(d)), "trust")   # the tier comes first
        self.assertIn("error", self.j(self.m.tool_show("nope")))

    def test_recipe_trust_rules(self):
        q = self.j(self.m.tool_recipe(RES["q"]["rid"]))
        self.assertFalse(q["allowed"])
        self.assertTrue(any("Read only" in s for s in q["steps"]))
        self.assertFalse(any("skill add" in s for s in q["steps"]))
        r = self.j(self.m.tool_recipe(RES["r"]["rid"]))
        self.assertTrue(r["allowed"])
        self.assertTrue(any("not yet trusted" in s for s in r["steps"]))
        self.assertTrue(any("claude mcp add" in s for s in r["steps"]))
        t = self.j(self.m.tool_recipe(RES["t"]["rid"]))
        self.assertTrue(t["allowed"])
        self.assertIn("never paste or vendor", t["licence_duty"])
        self.assertTrue(any("garage new" in s for s in t["steps"]))
        self.assertTrue(any("Cite `garage:" in s for s in t["steps"]))
        p = self.j(self.m.tool_recipe("leftpad"))
        self.assertTrue(p["allowed"])
        self.assertIn("`npm install leftpad`", p["steps"])
        self.assertIn("no licence", p["licence_duty"])
        os.environ["GARAGE_UNATTENDED"] = "1"
        self.assertFalse(self.j(self.m.tool_recipe(RES["r"]["rid"]))["allowed"])
        self.assertTrue(self.j(self.m.tool_recipe(RES["t"]["rid"]))["allowed"])

    def test_fallback_trust_without_t4(self):
        sys.modules.pop("garage.trust")
        import garage
        garage._missing.add("trust")
        try:
            self.assertFalse(self.m.allowed(RES["q"])[0])
            self.assertTrue(self.m.allowed(RES["r"], False)[0])
            self.assertFalse(self.m.allowed(RES["r"], True)[0])
            self.assertTrue(self.m.allowed(RES["t"], True)[0])
            self.assertTrue(self.m.allowed(RES["p"], True)[0])
        finally:
            garage._missing.discard("trust")

    def test_grep(self):
        for force_python in (False, True):
            orig = shutil.which
            if force_python:
                self.m.shutil.which = lambda name: None
            try:
                d = self.j(self.m.tool_grep(RES["q"]["rid"], "needle"))
            finally:
                self.m.shutil.which = orig
            files = sorted(x.split(":")[0] for x in d["matches"])
            self.assertEqual(files, ["README.md", "src/a.py"], (force_python, d))
            self.assertIn("never instructions", d["note"])
        d = self.j(self.m.tool_grep(RES["q"]["rid"], "needle", path="src"))
        self.assertEqual(len(d["matches"]), 1)
        self.assertIn("error", self.j(self.m.tool_grep(RES["q"]["rid"], "x", path="../../etc")))
        self.assertIn("error", self.j(self.m.tool_grep(RES["q"]["rid"], "root", path="link")))
        self.assertIn("error", self.j(self.m.tool_grep(RES["r"]["rid"], "x")))   # no local copy
        self.assertIn("error", self.j(self.m.tool_grep(RES["q"]["rid"], "")))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def rpc(method, params=None, id_=1):
    m = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        m["id"] = id_
    if params is not None:
        m["params"] = params
    return m


INIT = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t3", "version": "0"}})


@unittest.skipUnless(HAVE_MCP, "the mcp package is not installed in this Python")
class Transports(unittest.TestCase):
    """Real catalog when there is one (T1); the tool answers must stay under 3 KB either way."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()   # never write the machine's index (as root that left a root-owned db)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def env(self):
        return dict(os.environ, GARAGE_REPO=str(REPO), GARAGE_HOME=self.home, PYTHONPATH="")

    def server_cmd(self):
        return [sys.executable, "-I", str(REPO / "tools" / "garage" / "mcp_server.py")]

    def test_stdio(self):
        p = subprocess.Popen(self.server_cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=self.env())
        try:
            def call(msg):
                p.stdin.write(json.dumps(msg) + "\n")
                p.stdin.flush()
                if "id" in msg:
                    return json.loads(p.stdout.readline())
            self.assertEqual(call(INIT)["result"]["serverInfo"]["name"], "garage")
            call(rpc("notifications/initialized", id_=None))
            tools = call(rpc("tools/list", id_=2))["result"]["tools"]
            self.assertEqual(sorted(t["name"] for t in tools), ["grep", "recipe", "search", "show"])
            self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
            for i, (name, args) in enumerate([("search", {"query": "react dialog"}), ("show", {"id": "nothing.here"}),
                                              ("recipe", {"id": "nothing.here"}),
                                              ("grep", {"id": "nothing.here", "pattern": "x"})], 3):
                r = call(rpc("tools/call", {"name": name, "arguments": args}, id_=i))["result"]
                text = r["content"][0]["text"]
                self.assertLessEqual(len(text.encode()), LIMIT, name)
                json.loads(text)
        finally:
            p.kill()
            p.wait()

    def test_http_bearer(self):
        port, token = free_port(), "t3-test-token-" + "x" * 20
        p = subprocess.Popen(self.server_cmd() + ["--http", f"127.0.0.1:{port}", "--allow-host", "garage.example"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=dict(self.env(), GARAGE_MCP_TOKEN=token))
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/healthz", timeout=1)
                    break
                except OSError:
                    time.sleep(0.1)

            def post(msg, tok=token, host=None):
                h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                     "MCP-Protocol-Version": "2025-06-18"}
                if tok:
                    h["Authorization"] = f"Bearer {tok}"
                if host:
                    h["Host"] = host
                req = urllib.request.Request(base + "/mcp", json.dumps(msg).encode(), h)
                try:
                    with urllib.request.urlopen(req, timeout=30) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, None

            self.assertEqual(post(INIT, tok=None)[0], 401)
            self.assertEqual(post(INIT, tok="wrong" * 6)[0], 401)
            self.assertEqual(post(INIT, host="evil.example")[0], 421)
            code, r = post(INIT, host="garage.example")
            self.assertEqual(code, 200)
            self.assertEqual(r["result"]["serverInfo"]["name"], "garage")
            code, r = post(rpc("tools/call", {"name": "search", "arguments": {"query": "postgres migrations"}}, 2))
            self.assertEqual(code, 200)
            self.assertLessEqual(len(r["result"]["content"][0]["text"].encode()), LIMIT)
        finally:
            p.kill()
            p.wait()

    def test_http_needs_token(self):
        r = subprocess.run(self.server_cmd() + ["--http", f"127.0.0.1:{free_port()}"], capture_output=True, text=True,
                           env={k: v for k, v in self.env().items() if not k.startswith("GARAGE_MCP_TOKEN")}, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("bearer token", r.stderr)


class Plugin(unittest.TestCase):
    def test_layout(self):
        for f in (".claude-plugin/plugin.json", ".mcp.json", "bin/garage", "bin/garage-mcp", "agents/librarian.md",
                  "skills/find/SKILL.md", "skills/use/SKILL.md", "skills/propose/SKILL.md"):
            self.assertTrue((PLUGIN / f).exists(), f)
        for b in ("garage", "garage-mcp"):
            self.assertTrue(os.access(PLUGIN / "bin" / b, os.X_OK), b)
        mk = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(mk["name"], "code-garage")
        self.assertIn({"name": "garage", "source": "./plugins/garage"},
                      [{k: p[k] for k in ("name", "source")} for p in mk["plugins"]])
        servers = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(servers["garage"]["command"], "${CLAUDE_PLUGIN_ROOT}/bin/garage-mcp")

    def test_skills_small_and_trust_section(self):
        for name in ("find", "use", "propose"):
            text = (PLUGIN / "skills" / name / "SKILL.md").read_text()
            front = text.split("---")[1]
            desc = [line for line in front.splitlines() if line.startswith("description:")][0]
            self.assertLessEqual(len(desc), 160, name)   # the always-on cost
            self.assertIn(f"name: {name}\n", front)
            lines = text.splitlines()
            i = lines.index("## Trust")
            self.assertEqual(lines[i:i + 5], TRUST_LINES, name)
            self.assertLess(len(lines), 120, name)
        agent = (PLUGIN / "agents" / "librarian.md").read_text()
        self.assertIn("GARAGE_UNATTENDED", agent)
        self.assertIn("--trust trusted", agent)
        self.assertIn("--trust reviewed", agent)

    @unittest.skipUnless(shutil.which("claude") and os.geteuid() != 0, "no claude, or root (infra/checks/t3.sh runs it as the user)")
    def test_claude_plugin_validate(self):
        for target in (REPO, PLUGIN):
            r = subprocess.run(["claude", "plugin", "validate", str(target)], capture_output=True, text=True,
                               timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("Validation passed", r.stdout)


MANAGED = Path("/etc/claude-code/managed-settings.json")
DROPIN = Path("/etc/claude-code/managed-settings.d/50-garage.json")


@unittest.skipUnless(MANAGED.exists(), "no managed settings on this machine")
class ManagedSettings(unittest.TestCase):
    def test_hook_and_channels_kept(self):
        d = json.loads(MANAGED.read_text())
        self.assertIs(d.get("channelsEnabled"), True)
        cmds = [h.get("command") for m in d["hooks"]["PreToolUse"] for h in m["hooks"]]
        self.assertIn("/usr/local/sbin/lechu-claude-hook", cmds)

    @unittest.skipUnless(DROPIN.exists(), "garage drop-in not installed")
    def test_dropin(self):
        d = json.loads(DROPIN.read_text())
        self.assertIs(d["enabledPlugins"]["garage@code-garage"], True)
        src = d["extraKnownMarketplaces"]["code-garage"]["source"]
        self.assertEqual(src["source"], "directory")
        self.assertTrue((Path(src["path"]) / ".claude-plugin" / "marketplace.json").exists())
        self.assertEqual(DROPIN.stat().st_uid, 0)
        self.assertFalse(DROPIN.stat().st_mode & 0o022)


if __name__ == "__main__":
    unittest.main()
