"""T2 (pins, mirror, verify) tests. Offline: a local git repo stands in for GitHub (GARAGE_GIT_BASE=file://...),
GraphQL and lychee answers come from fixtures. Run: python3 -I -m unittest discover -s tests/t2"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from garage import catalog, mirror, pins, verify  # noqa: E402

GENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
CATALOG = """slice: test
generated: 2026-10-29
topics:
  - id: test.area.one
    title: One
    area: area
    why: "test"
    resources:
      - name: demo skill
        url: https://github.com/acme/tools/tree/HEAD/skills/demo
        kind: skill
        license: MIT
        tier: 2
        use: skill
        path: skills/demo
      - name: acme tools
        url: https://github.com/acme/tools
        kind: repo
        license: MIT
        stars: 100
        pushed: 2026-01-01
        archived: false
        tier: 1
        use: reference
        note: "Tools of acme."
      - name: docs only
        url: https://github.com/acme/docs
        kind: docs
        license: MIT
        stars: 5
        pushed: 2026-01-01
        archived: false
        tier: 2
        use: reference
        note: "Docs."
      - name: no licence
        url: https://github.com/acme/nolic
        kind: repo
        license: none
        tier: 3
        use: vendor
      - name: a site
        url: https://example.org/guide
        kind: guide
        license: none
        tier: 2
        use: reference
"""


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, env=GENV, check=True,
                   capture_output=True)


def make_upstream(base, name, files, links=()):
    d = base / name
    d.mkdir(parents=True)
    git(d, "init", "-q", "-b", "main")
    for rel, (content, mode) in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        os.chmod(p, mode)
    for rel, target in links:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, d / rel)
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "one")
    git(d, "config", "uploadpack.allowAnySHA1InWant", "true")
    git(d, "config", "uploadpack.allowFilter", "true")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, env=GENV, capture_output=True, text=True).stdout.strip()


class Fake:
    def __init__(self, tiers=None):
        self.tiers = tiers or {}

    def tier(self, rid):
        return self.tiers.get(rid, "quarantine")


class T2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.home, self.repo, up = t / "home", t / "repo", t / "up"
        for d in ("mirror", "quarantine", "state"):
            (self.home / d).mkdir(parents=True)
        (self.repo / "catalog").mkdir(parents=True)
        (self.repo / "catalog" / "test.yaml").write_text(CATALOG)
        self.sha = make_upstream(up, "acme/tools", {
            "LICENSE": (b"MIT License\n", 0o644),
            "NOTICE": (b"acme notice\n", 0o644),
            "README.md": (b"# tools\n", 0o644),
            "skills/demo/SKILL.md": (b"---\nname: demo\n---\n", 0o644),
            "skills/demo/run.sh": (b"#!/bin/sh\necho hi\n", 0o755),
            "Web-Shells/shell.php": (b"<?php system($_GET['c']); ?>", 0o644),
            "big.bin": (b"\0" * (2 * 1024 * 1024), 0o644),
            "docs/guide.md": (b"guide\n", 0o644),
        }, links=[("skills/demo/escape", "/etc/passwd"), ("skills/demo/inside", "SKILL.md")])
        self.dsha = make_upstream(up, "acme/docs", {"README.md": (b"# docs\n", 0o644),
                                                    "docs/a.md": (b"a\n", 0o644), "src/x.c": (b"int x;\n", 0o644)})
        self.env = mock.patch.dict(os.environ, {"GARAGE_HOME": str(self.home), "GARAGE_REPO": str(self.repo),
                                                "GARAGE_GIT_BASE": f"file://{up}/"})
        self.env.start()
        catalog._cache.clear()
        pins._cache.clear()
        p = {}
        cat = catalog.load()
        for rid, res in cat["resources"].items():
            r = pins.repo_of(res["url"])
            if not r:
                continue
            sha = self.sha if r[0] == "acme/tools" else self.dsha
            lic = "none" if r[0] == "acme/nolic" else "MIT"
            path = pins.path_of(res)
            p[rid] = {"repo": r[0], "sha": sha, "path": path, "pinned": "2026-10-29", "license_at_pin": lic,
                      "size_kb": 10, "policy": pins.policy_for(res, lic, 10, path)}
        pins.dump(p)
        self.pins = pins.load()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    # --- pins ---
    def test_schema_matches_code_and_lock(self):
        schema = json.loads((ROOT / "schema" / "pins.schema.json").read_text())
        pin = schema["$defs"]["pin"]
        self.assertEqual(sorted(pin["required"]), sorted(pins.FIELDS))
        self.assertEqual(pin["properties"]["policy"]["enum"], list(pins.POLICIES))
        self.assertEqual(pins.validate(self.pins), [])
        real = ROOT / "lock" / "pins.yaml"
        if real.is_file():
            import yaml
            data = yaml.safe_load(real.read_text())
            self.assertEqual(pins.validate(data), [])
            try:
                import jsonschema
            except ImportError:
                return
            jsonschema.validate({k: {kk: (vv.isoformat() if hasattr(vv, "isoformat") else vv)
                                     for kk, vv in v.items()} for k, v in data.items()}, schema)

    def test_schema_rejects_bad_pins(self):
        good = next(iter(self.pins.values()))
        for bad, word in ((dict(good, sha="abc123"), "sha"), (dict(good, policy="all"), "policy"),
                          (dict(good, extra=1), "unknown"), (dict(good, path="../x"), "path"),
                          ({k: v for k, v in good.items() if k != "size_kb"}, "missing")):
            errs = pins.validate({"https://github.com/a/b": bad})
            self.assertTrue(any(word in e for e in errs), (word, errs))

    def test_policy(self):
        self.assertEqual({r: p["policy"] for r, p in self.pins.items()}, {
            "https://github.com/acme/tools/tree/HEAD/skills/demo": "snapshot",
            "https://github.com/acme/tools": "readme",
            "https://github.com/acme/docs": "readme",
            "https://github.com/acme/nolic": "link"})
        self.assertEqual(pins.policy_for({"use": "vendor"}, "MIT", pins.GIANT_KB + 1, ""), "readme")
        self.assertEqual(pins.policy_for({"use": "vendor"}, "MIT", pins.GIANT_KB + 1, "src"), "snapshot")
        self.assertEqual(pins.policy_for({"use": "skill", "license": "Apache-2.0"}, "NOASSERTION", 1, ""),
                         "snapshot")

    def test_pin_command_and_fork_gotcha(self):
        from garage import pin
        node = {"nameWithOwner": "acme/tools", "isArchived": False, "isFork": False, "diskUsage": 42,
                "pushedAt": "2026-10-01T00:00:00Z", "stargazerCount": 1, "licenseInfo": {"spdxId": "MIT"},
                "defaultBranchRef": {"name": "main", "target": {"oid": "c" * 40}}}
        fx = Path(self.tmp.name) / "gh.json"
        fx.write_text(json.dumps({"acme/tools": node, "acme/docs": dict(node, nameWithOwner="acme/docs"),
                                  "acme/nolic": dict(node, nameWithOwner="acme/nolic", licenseInfo=None)}))
        with mock.patch.dict(os.environ, {"GARAGE_GH_FIXTURE": str(fx)}), mock.patch("sys.stdout"):
            pins.dump({})
            self.assertEqual(pin.main([]), 0)
            new = pins.load()
            self.assertEqual(len(new), 4)
            self.assertTrue(all(p["sha"] == "c" * 40 for p in new.values()))
            self.assertEqual(new["https://github.com/acme/nolic"]["policy"], "link")
            self.assertEqual(new["https://github.com/acme/tools"]["size_kb"], 42)
            node["defaultBranchRef"]["target"]["oid"] = "d" * 40
            fx.write_text(json.dumps({"acme/tools": node}))
            self.assertEqual(pin.main([]), 0)                       # pins never move on their own
            self.assertEqual(pins.load()["https://github.com/acme/tools"]["sha"], "c" * 40)
            rid = "https://github.com/acme/tools/tree/HEAD/skills/demo"
            with mock.patch.object(pin, "compare_status", return_value="diverged"):
                self.assertEqual(pin.main(["--set", rid, "b" * 40]), 1)   # a fork-only sha is refused
            with mock.patch.object(pin, "compare_status", return_value="behind"):
                self.assertEqual(pin.main(["--set", rid, "b" * 40]), 0)
            self.assertEqual(pins.load()[rid]["sha"], "b" * 40)
            with mock.patch.object(pin, "compare_status", return_value="ahead"):
                self.assertEqual(pin.main(["--check-forks"]), 1)

    # --- mirror ---
    def run_mirror(self, tiers=None):
        with mock.patch.object(mirror, "_trust", return_value=Fake(tiers)):
            return mirror.main(["--no-prune"])

    def test_quarantine_placement_sanitising_and_promotion(self):
        self.assertEqual(self.run_mirror(), 0)
        q = self.home / "quarantine" / "acme__tools" / self.sha[:12]
        self.assertTrue((q / ".garage.json").is_file())
        self.assertEqual(os.readlink(q.parent / "current"), self.sha[:12])
        self.assertFalse((self.home / "mirror" / "acme__tools").exists())
        self.assertTrue((self.home / "mirror" / "acme__docs" / self.dsha[:12] / "docs" / "a.md").is_file())
        self.assertFalse((self.home / "mirror" / "acme__docs" / self.dsha[:12] / "src").exists())  # readme policy
        meta = json.loads((q / ".garage.json").read_text())
        self.assertEqual(meta["sha"], self.sha)
        self.assertEqual(meta["location"], "quarantine")
        self.assertIn("skills/demo/SKILL.md", meta["files"])
        self.assertEqual(meta["manifest_sha256"], mirror.manifest_sha(meta["files"]))
        reasons = {e["path"]: e["reason"] for e in meta["excluded"]}
        self.assertEqual(reasons.get("skills/demo/escape"), "symlink outside the snapshot")
        self.assertTrue((q / "skills/demo/inside").is_symlink())
        self.assertFalse((q / "big.bin").exists())          # not in the sparse patterns anyway
        self.assertFalse((q / "Web-Shells").exists())
        run = q / "skills/demo/run.sh"
        self.assertEqual(stat.S_IMODE(run.stat().st_mode) & 0o111, 0)   # exec bits stripped in quarantine
        self.assertEqual(meta["files"]["skills/demo/run.sh"][2], 0o755)
        self.assertEqual(mirror.local_path("https://github.com/acme/tools/tree/HEAD/skills/demo"),
                         str(q / "skills/demo"))
        self.assertEqual(mirror.check(), [])
        # reviewed -> the next run moves it to mirror/ and restores the exec bit
        tiers = {"https://github.com/acme/tools/tree/HEAD/skills/demo": "reviewed"}
        self.assertEqual(self.run_mirror(tiers), 0)
        m = self.home / "mirror" / "acme__tools" / self.sha[:12]
        self.assertTrue((m / ".garage.json").is_file())
        self.assertFalse(q.exists())
        self.assertEqual(stat.S_IMODE((m / "skills/demo/run.sh").stat().st_mode), 0o755)

    def test_payload_folder_and_binary_cap_in_full_snapshot(self):
        work = Path(self.tmp.name) / "w"
        mirror.git_fetch("acme/tools", self.sha, [], work)
        files, excluded = mirror.sanitize(work, "acme/tools", strip_exec=True)
        reasons = {e["path"]: e["reason"] for e in excluded}
        self.assertEqual(reasons["Web-Shells"], "payload folder")
        self.assertEqual(reasons["big.bin"], "archive/binary > 1 MB")
        self.assertFalse((work / ".git").exists())
        self.assertIn("LICENSE", files)

    def test_sha_mismatch_caught(self):
        bogus = "0" * 39 + "1"
        u = {"repo": "acme/tools", "sha": bogus, "rids": [], "paths": [], "full": True, "docs": False,
             "policy": "snapshot", "pinned": "2026-10-29", "license": "MIT", "license_at_pin": "MIT", "size_kb": 1,
             "location": "quarantine", "patterns": [], "tiers": {}}
        r = mirror.mirror_unit(u)
        self.assertFalse(r["ok"])
        self.assertFalse((self.home / "quarantine" / "acme__tools" / bogus[:12]).exists())
        # a snapshot on disk whose .garage.json disagrees with the pin is reported, and the run refetches it
        self.assertEqual(self.run_mirror(), 0)
        q = self.home / "quarantine" / "acme__tools" / self.sha[:12] / ".garage.json"
        meta = json.loads(q.read_text())
        meta["sha"] = "f" * 40
        q.write_text(json.dumps(meta))
        with mock.patch.object(mirror, "_trust", return_value=Fake()):
            probs = mirror.check()
        self.assertTrue(any("sha mismatch" in p for p in probs), probs)
        self.assertEqual(self.run_mirror(), 0)
        self.assertEqual(json.loads(q.read_text())["sha"], self.sha)
        # deep check: a changed file differs from the manifest
        f = q.parent / "README.md"
        os.chmod(f, 0o644)
        f.write_text("tampered\n")
        with mock.patch.object(mirror, "_trust", return_value=Fake()):
            self.assertTrue(any("differs" in p for p in mirror.check(deep=True)))
        # vendir's lock must name the pinned sha: a fake vendir that locks another commit is caught, and the unit
        # falls back to git fetch-by-sha
        fake = Path(self.tmp.name) / "vendir"
        fake.write_text('#!/bin/sh\ncd "$3" && mkdir -p out && echo x > out/f && printf "directories:\\n- contents:'
                        '\\n  - git: {sha: %s}\\n" > vendir.lock.yml\n' % ("e" * 40))
        fake.chmod(0o755)
        with mock.patch.object(mirror, "VENDIR", str(fake)):
            with self.assertRaisesRegex(RuntimeError, "sha mismatch"):
                mirror.vendir_fetch(dict(u, sha=self.sha), Path(self.tmp.name) / "v")
            shutil.rmtree(q.parent)
            r = mirror.mirror_unit(dict(u, sha=self.sha), engine="vendir")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["engine"], "git")

    def test_fetch_keeps_license_offline_and_from_mirror(self):
        rid = "https://github.com/acme/tools/tree/HEAD/skills/demo"
        dest = Path(self.tmp.name) / "proj" / "vendor" / "demo"
        out = Path(mirror.fetch(rid, dest))          # nothing mirrored: fetched by sha into $GARAGE_HOME/cache
        self.assertEqual(out, dest)
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertEqual((dest / "LICENSE").read_text(), "MIT License\n")
        self.assertTrue((dest / "NOTICE").is_file())
        self.assertEqual(stat.S_IMODE((dest / "run.sh").stat().st_mode), 0o755)
        meta = json.loads((dest / ".garage.json").read_text())
        self.assertEqual((meta["sha"], meta["path"], meta["source"]), (self.sha, "skills/demo", "github"))
        self.assertIn("LICENSE", meta["license_files"])
        self.assertFalse((dest / "escape").exists())
        with self.assertRaises(FileExistsError):
            mirror.fetch(rid, dest)
        with self.assertRaises(PermissionError):
            mirror.fetch("https://github.com/acme/nolic", Path(self.tmp.name) / "x")
        self.run_mirror()                              # now from the local quarantine copy, modes restored
        d2 = Path(self.tmp.name) / "proj2"
        mirror.fetch(rid, d2)
        self.assertEqual(json.loads((d2 / ".garage.json").read_text())["source"], "mirror")
        self.assertEqual(stat.S_IMODE((d2 / "run.sh").stat().st_mode), 0o755)
        self.assertTrue((d2 / "LICENSE").is_file())

    # --- verify ---
    def test_verify_dry_run_flags_archived_from_fixture(self):
        node = lambda name, arch: {"nameWithOwner": name, "isArchived": arch, "pushedAt": "2026-10-01T00:00:00Z",  # noqa
                                   "stargazerCount": 100, "licenseInfo": {"spdxId": "MIT"},
                                   "defaultBranchRef": {"name": "main", "target": {"oid": "a" * 40}}}
        fx = Path(self.tmp.name) / "gh.json"
        fx.write_text(json.dumps({"acme/tools": node("acme/tools", True), "acme/docs": node("acme-org/docs", False),
                                  "acme/nolic": None}))
        lf = Path(self.tmp.name) / "ly.json"
        lf.write_text(json.dumps({"https://example.org/guide": "404 Not Found"}))
        out = Path(self.tmp.name) / "reports"
        with mock.patch.dict(os.environ, {"GARAGE_GH_FIXTURE": str(fx), "GARAGE_LYCHEE_FIXTURE": str(lf)}):
            with mock.patch("sys.stdout"):
                self.assertEqual(verify.main(["--dry-run", "--out", str(out), "--week", "2026-W44"]), 0)
        rep = (out / "verify-2026-W44.md").read_text().splitlines()
        self.assertLessEqual(len(rep), 20)
        text = "\n".join(rep)
        self.assertIn("| archived | 1 | acme/tools |", text)
        self.assertIn("acme/docs -> acme-org/docs", text)
        self.assertIn("| gone | 1 | acme/nolic |", text)
        self.assertIn("| dead links | 1 | https://example.org/guide |", text)
        self.assertEqual(subprocess.run(["git", "status"], cwd=self.repo, capture_output=True).returncode != 0, True)
        self.assertEqual((self.repo / "catalog" / "test.yaml").read_text(), CATALOG)   # dry run: catalog untouched
        f = json.loads((self.home / "state" / "verify-2026-W44.json").read_text())
        by = {x["url"]: x["changes"] for x in f["metadata"]}
        new, n = verify.edit_yaml(CATALOG, by)
        import yaml
        res = {r["url"]: r for r in yaml.safe_load(new)["topics"][0]["resources"]}
        self.assertTrue(res["https://github.com/acme/tools"]["archived"])
        self.assertEqual(res["https://github.com/acme/tools"]["tier"], 3)
        self.assertTrue(res["https://github.com/acme/tools"]["note"].startswith("ARCHIVED upstream"))
        self.assertIn("https://github.com/acme-org/docs", res)
        self.assertEqual(len(res), 5)


if __name__ == "__main__":
    unittest.main()
