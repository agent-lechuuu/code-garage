"""Shared fixtures for the T4 (safety) tests: a throwaway GARAGE_HOME + GARAGE_REPO with a tiny catalog and pins."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
FIXTURES = HERE / "fixtures"

SHA = "a" * 40
SHA2 = "b" * 40
SKILL_URL = "https://github.com/acme/skills/tree/main/skills/tidy"   # as written in the catalog
SKILL = "https://github.com/acme/skills/tree/HEAD/skills/tidy"       # its rid (garage.catalog.normalize_url)
GPL_VENDOR = "https://github.com/acme/gpl-lib"
MIT_VENDOR = "https://github.com/acme/mit-lib"
DOCS = "https://github.com/acme/handbook"

CATALOG = f"""slice: test
generated: 2026-10-29
topics:
  - id: test.area.skills
    title: Test skills
    area: area
    why: "for tests"
    resources:
      - {{name: tidy, url: {SKILL_URL}, kind: skill, license: MIT, tier: 1, use: skill, note: "commit messages"}}
      - {{name: gpl-lib, url: {GPL_VENDOR}, kind: repo, license: GPL-3.0, tier: 2, use: vendor, note: "x"}}
      - {{name: mit-lib, url: {MIT_VENDOR}, kind: repo, license: MIT, tier: 2, use: vendor, note: "x"}}
      - {{name: handbook, url: {DOCS}, kind: guide, license: MIT, tier: 2, use: reference, note: "x"}}
"""


def pin(repo, sha=SHA, path="", lic="MIT", policy="snapshot"):
    return {"repo": repo, "sha": sha, "path": path, "pinned": "2026-10-29", "license_at_pin": lic, "size_kb": 10,
            "policy": policy}


PINS = {SKILL: pin("acme/skills", path="skills/tidy"), GPL_VENDOR: pin("acme/gpl-lib", lic="GPL-3.0"),
        MIT_VENDOR: pin("acme/mit-lib"), DOCS: pin("acme/handbook", policy="readme")}


def scans(result="pass"):
    return [{"tool": t, "version": "1", "date": "2026-10-29", "result": result if t == "aguara" else "pass",
             "findings": 0} for t in ("skillspector", "aguara", "gitleaks", "garage-checks")]


def reviewed(sha=SHA, result="pass"):
    return {"trust": "reviewed", "sha": sha, "scans": scans(result), "reviewed_by": "test", "reviewed": "2026-10-29",
            "notes": "ok", "summary": "tidy commit messages", "can": {"shell": True, "network": False,
                                                                       "files": False, "secrets": False}}


class GarageCase(unittest.TestCase):
    """A fresh garage per test: GARAGE_HOME/GARAGE_REPO point into a temp dir."""

    def setUp(self):
        import yaml
        self.tmp = Path(tempfile.mkdtemp(prefix="garage-t4-"))
        self.home, self.repo = self.tmp / "home", self.tmp / "repo"
        for d in ("catalog", "lock", "trust"):
            (self.repo / d).mkdir(parents=True)
        for d in ("state", "mirror", "quarantine"):
            (self.home / d).mkdir(parents=True)
        (self.repo / "catalog" / "test.yaml").write_text(CATALOG)
        (self.repo / "lock" / "pins.yaml").write_text(yaml.safe_dump(PINS))
        self.write_registry({})
        self._env = {k: os.environ.get(k) for k in ("GARAGE_HOME", "GARAGE_REPO", "GARAGE_UNATTENDED")}
        os.environ.update(GARAGE_HOME=str(self.home), GARAGE_REPO=str(self.repo))
        os.environ.pop("GARAGE_UNATTENDED", None)
        from garage import catalog, pins, trust
        for m in (catalog, pins, trust):
            m._cache.clear()

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_registry(self, reg):
        import yaml
        (self.repo / "trust" / "registry.yaml").write_text("# test\n" + yaml.safe_dump(reg))
        try:
            from garage import trust
            trust._cache.clear()
        except ImportError:
            pass

    def snapshot(self, rid, src):
        """Place a fixture folder as the quarantined snapshot of rid (the T2 layout + .garage.json)."""
        import json
        p = PINS[rid]
        unit = self.home / "quarantine" / p["repo"].replace("/", "__").lower() / p["sha"][:12]
        dest = unit / p["path"] if p["path"] else unit
        shutil.copytree(src, dest)
        (unit / ".garage.json").write_text(json.dumps({"repo": p["repo"], "sha": p["sha"]}))
        return dest
