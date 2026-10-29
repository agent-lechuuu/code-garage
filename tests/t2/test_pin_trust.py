"""Every pin move (garage pin --bump / --bump-all / --set) drops the item's trust record to quarantine
(garage.trust.reset) before lock/pins.yaml is written, and garage.policy.check stays green afterwards.
Offline: GraphQL from a fixture, compare status mocked. Run: python3 -I -m unittest discover -s tests/t2"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from garage import catalog, pin, pins, policy, trust  # noqa: E402

from test_t2 import CATALOG  # noqa: E402

SKILL = "https://github.com/acme/tools/tree/HEAD/skills/demo"
OLD, NEW, SET = "a" * 40, "c" * 40, "b" * 40


def node(head):
    return {"nameWithOwner": "acme/tools", "isArchived": False, "isFork": False, "diskUsage": 42,
            "pushedAt": "2026-10-01T00:00:00Z", "stargazerCount": 1, "licenseInfo": {"spdxId": "MIT"},
            "defaultBranchRef": {"name": "main", "target": {"oid": head}}}


def reviewed(sha):
    scans = [{"tool": t, "version": "1", "date": "2026-10-29", "result": "pass", "findings": 0}
             for t in ("skillspector", "aguara", "gitleaks", "garage-checks")]
    return {"trust": "reviewed", "sha": sha, "scans": scans, "reviewed_by": "test", "reviewed": "2026-10-29",
            "notes": "ok"}


class PinMovesResetTrust(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.home, self.repo = t / "home", t / "repo"
        (self.home / "state").mkdir(parents=True)
        (self.repo / "catalog").mkdir(parents=True)
        (self.repo / "catalog" / "test.yaml").write_text(CATALOG)
        self.fx = t / "gh.json"
        self.fx.write_text(json.dumps({"acme/tools": node(NEW)}))
        self.env = mock.patch.dict(os.environ, {"GARAGE_HOME": str(self.home), "GARAGE_REPO": str(self.repo),
                                                "GARAGE_GH_FIXTURE": str(self.fx), "GARAGE_TRUST_GIT": "0"})
        self.env.start()
        for m in (catalog, pins, trust):
            m._cache.clear()
        cat = catalog.load()
        p = {}
        for rid, res in cat["resources"].items():
            r = pins.repo_of(res["url"])
            if r and r[0] == "acme/tools":
                path = pins.path_of(res)
                p[rid] = {"repo": r[0], "sha": OLD, "path": path, "pinned": "2026-10-29", "license_at_pin": "MIT",
                          "size_kb": 10, "policy": pins.policy_for(res, "MIT", 10, path)}
        pins.dump(p)
        trust.put(SKILL, reviewed(OLD), "test")
        self.assertEqual(trust.tier(SKILL), "reviewed")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def policy_errors(self):
        for m in (catalog, pins, trust):
            m._cache.clear()
        # (the shared fixture also holds a no-licence vendor item: only acme/tools' rids matter here)
        return [e for e in policy.check(catalog.load(), pins.all(), trust.load())
                if e.startswith("https://github.com/acme/tools")]

    def test_bump_resets_and_policy_stays_green(self):
        self.assertEqual(self.policy_errors(), [])
        with mock.patch("sys.stdout"):
            self.assertEqual(pin.main(["--bump", "acme/tools", "--dry-run"]), 0)
        self.assertEqual(pins.load()[SKILL]["sha"], OLD)                 # dry run: nothing moved, nothing reset
        self.assertEqual(trust.record(SKILL)["trust"], "reviewed")
        with mock.patch("sys.stdout"):
            self.assertEqual(pin.main(["--bump", SKILL]), 0)
        self.assertEqual(pins.load()[SKILL]["sha"], NEW)
        rec = trust.record(SKILL)
        self.assertEqual(rec["trust"], "quarantine")
        self.assertIn(f"pin {OLD[:12]} -> {NEW[:12]}", rec["reasons"][0])
        self.assertTrue(any("was reviewed" in h for h in rec["history"]))
        self.assertEqual(trust.tier(SKILL), "quarantine")
        self.assertEqual(self.policy_errors(), [])

    def test_bump_all_resets(self):
        with mock.patch("sys.stdout"):
            self.assertEqual(pin.main(["--bump-all"]), 0)
        self.assertEqual(trust.record(SKILL)["trust"], "quarantine")
        self.assertEqual(self.policy_errors(), [])

    def test_set_resets_and_policy_stays_green(self):
        with mock.patch.object(pin, "compare_status", return_value="behind"), mock.patch("sys.stdout"):
            self.assertEqual(pin.main(["--set", SKILL, SET]), 0)
        self.assertEqual(pins.load()[SKILL]["sha"], SET)
        self.assertEqual(trust.record(SKILL)["trust"], "quarantine")
        self.assertEqual(self.policy_errors(), [])

    def test_without_reset_policy_would_fail(self):
        """The guard the reset satisfies: a reviewed record for an old sha is a policy error."""
        p = dict(pins.load())
        p[SKILL] = dict(p[SKILL], sha=NEW)
        pins.dump(p)
        self.assertTrue(any(e.startswith(SKILL) and "re-review" in e for e in self.policy_errors()))

    def test_unchanged_pin_keeps_trust(self):
        self.fx.write_text(json.dumps({"acme/tools": node(OLD)}))
        with mock.patch("sys.stdout"):
            self.assertEqual(pin.main(["--bump-all"]), 0)
            self.assertEqual(pin.main([]), 0)
        self.assertEqual(trust.record(SKILL)["trust"], "reviewed")


if __name__ == "__main__":
    unittest.main()
