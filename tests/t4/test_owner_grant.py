"""The owner's permission for the owner's own unlicensed repos (LicenseRef-owner-grant, 2026-10-30): vendoring is
allowed only on the owner's accounts, only with a license_note, and it never counts as a permissive licence."""
import unittest

import helpers  # noqa: F401 - puts tools/ on sys.path
from garage import catalog, policy

NOTE = "The owner allows copying it into the owner's own projects."


def cat(url, **res):
    r = dict({"name": "x", "url": url, "kind": "snippet", "license": catalog.OWNER_GRANT, "license_note": NOTE,
              "tier": 3, "use": "vendor"}, **res)
    return {"topics": [], "resources": {catalog.normalize_url(url): r}}


class OwnerGrant(unittest.TestCase):
    def test_owner_repo_may_be_vendored(self):
        self.assertEqual(policy.check(cat("https://github.com/AaroneGeorge/First-Buy/blob/main/src/core/ssrf.ts"),
                                      {}, {}), [])

    def test_someone_elses_repo_is_refused(self):
        errs = policy.check(cat("https://github.com/acme/widget"), {}, {})
        self.assertTrue(any("only for the owner's own repos" in e for e in errs), errs)

    def test_needs_a_note(self):
        errs = policy.check(cat("https://github.com/AaroneGeorge/warden", license_note=""), {}, {})
        self.assertTrue(any("needs a license_note" in e for e in errs), errs)

    def test_not_permissive(self):
        self.assertFalse(catalog.is_permissive(catalog.OWNER_GRANT))
        self.assertIsNone(policy.licence_problem(catalog.OWNER_GRANT))
        self.assertIsNotNone(policy.licence_problem("none"))


if __name__ == "__main__":
    unittest.main()
