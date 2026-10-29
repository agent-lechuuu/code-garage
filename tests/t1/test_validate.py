"""T1: garage validate catches broken catalogs; the repo guard refuses what doesn't belong in git."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fixture
from garage import validate

DUP = fixture.BACKEND.replace("id: backend.jobs.queues", "id: backend.auth.sessions")
BAD_SEE = fixture.BACKEND.replace("see_also: [frontend.forms.validation]", "see_also: [frontend.forms.nope]")
SELF_SEE = fixture.BACKEND.replace("see_also: [frontend.forms.validation]", "see_also: [backend.auth.sessions]")
BAD_AREA = fixture.BACKEND.replace("area: jobs", "area: queues")
BAD_KIND = fixture.BACKEND.replace("kind: guide", "kind: blogpost")
BAD_PREFIX = fixture.BACKEND.replace("id: backend.jobs.queues", "id: frontend.jobs.queues")
TWICE = fixture.BACKEND.replace("url: https://lucia-auth.com/", "url: https://github.com/example/gpl-sessions")


def run(backend=None):
    extra = {"catalog/backend.yaml": backend} if backend else {}
    with fixture.Garage(extra), mock.patch.object(validate, "optional", fixture.fake_optional()):
        return validate.validate()


class Validate(unittest.TestCase):
    def test_fixture_is_valid(self):
        errors, warnings = run()
        self.assertEqual(errors, [])
        self.assertTrue(any("policy not installed" in w for w in warnings))

    def test_duplicate_id(self):
        errors, _ = run(DUP)
        self.assertTrue(any("duplicate topic id backend.auth.sessions" in e for e in errors), errors)

    def test_see_also_must_resolve(self):
        errors, _ = run(BAD_SEE)
        self.assertTrue(any("see_also frontend.forms.nope does not exist" in e for e in errors), errors)
        errors, _ = run(SELF_SEE)
        self.assertTrue(any("points to itself" in e for e in errors), errors)

    def test_area_kind_prefix_twice(self):
        self.assertTrue(any("area 'queues'" in e for e in run(BAD_AREA)[0]))
        self.assertTrue(any("'blogpost' not one of" in e for e in run(BAD_KIND)[0]))
        self.assertTrue(any("must start with the slice" in e for e in run(BAD_PREFIX)[0]))
        self.assertTrue(any("listed twice" in e for e in run(TWICE)[0]))

    def test_policy_is_called(self):
        calls = []

        class Policy:
            @staticmethod
            def check(cat, pins, trust):
                calls.append(len(cat["resources"]))
                return ["https://x: use vendor refused under licence GPL-3.0"]
        with fixture.Garage(), mock.patch.object(validate, "optional", fixture.fake_optional(policy=Policy)):
            errors, _ = validate.validate()
        self.assertEqual(calls, [8])
        self.assertEqual(errors, ["policy: https://x: use vendor refused under licence GPL-3.0"])

    def test_real_catalog(self):
        """The repo's own catalog passes (schema, ids, see_also), policy left to the policy tests."""
        with mock.patch.dict(os.environ, {"GARAGE_REPO": str(fixture.ROOT)}), \
                mock.patch.object(validate, "optional", fixture.fake_optional()):
            errors, _ = validate.validate(fixture.ROOT)
        self.assertEqual(errors, [])


class Guard(unittest.TestCase):
    def test_guard(self):
        with tempfile.TemporaryDirectory() as d:
            ok, db, big, log = (os.path.join(d, n) for n in ("a.yaml", "x.db", "big.json", "run.log"))
            Path(ok).write_text("a: 1\n")
            Path(db).write_bytes(b"SQLite format 3\0")
            with open(big, "wb") as f:
                f.truncate(validate.GUARD_MAX + 1)
            with open(log, "wb") as f:
                f.truncate(1_000_001)
            bad = validate.guard([ok, db, big, log, os.path.join(d, "missing.png")])
            self.assertEqual(len(bad), 3, bad)
            self.assertTrue(any("x.db" in b for b in bad) and any("big.json" in b for b in bad))


if __name__ == "__main__":
    unittest.main()
