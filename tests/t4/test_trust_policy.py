"""trust.allowed()/tier() and policy.check()."""
import unittest

from helpers import DOCS, GPL_VENDOR, MIT_VENDOR, PINS, SHA, SHA2, SKILL, GarageCase, reviewed


class TestTrust(GarageCase):
    def test_missing_record_is_quarantine_and_refused(self):
        from garage import trust
        self.assertEqual(trust.tier(SKILL), "quarantine")
        for unattended in (False, True):
            ok, why = trust.allowed(SKILL, unattended)
            self.assertFalse(ok)
            self.assertIn("quarantine", why)

    def test_reviewed_interactive_only(self):
        from garage import trust
        self.write_registry({SKILL: reviewed()})
        self.assertEqual(trust.tier(SKILL), "reviewed")
        self.assertTrue(trust.allowed(SKILL, False)[0])
        ok, why = trust.allowed(SKILL, True)
        self.assertFalse(ok)
        self.assertIn("unattended", why)

    def test_env_decides_when_unattended_is_none(self):
        import os
        from garage import trust
        self.write_registry({SKILL: reviewed()})
        os.environ["GARAGE_UNATTENDED"] = "1"
        self.assertFalse(trust.allowed(SKILL)[0])
        os.environ["GARAGE_UNATTENDED"] = "0"
        self.assertTrue(trust.allowed(SKILL)[0])

    def test_trusted_allowed_unattended(self):
        from garage import trust
        self.write_registry({SKILL: dict(reviewed(), trust="trusted", approved_by="owner", approved="2026-10-29",
                                         approval=12)})
        self.assertEqual(trust.tier(SKILL), "trusted")
        self.assertTrue(trust.allowed(SKILL, True)[0])

    def test_trusted_without_approval_counts_as_quarantine(self):
        from garage import trust
        self.write_registry({SKILL: dict(reviewed(), trust="trusted", approved_by="owner", approved="2026-10-29")})
        self.assertEqual(trust.tier(SKILL), "quarantine")
        self.assertFalse(trust.allowed(SKILL, True)[0])
        self.write_registry({SKILL: dict(reviewed(), trust="trusted", approved_by="me", approved="2026-10-29",
                                         approval=3)})
        self.assertEqual(trust.tier(SKILL), "quarantine")

    def test_pin_bump_drops_to_quarantine(self):
        from garage import trust
        self.write_registry({SKILL: dict(reviewed(sha=SHA2), trust="trusted", approved_by="owner",
                                         approved="2026-10-29", approval=12)})
        t, why = trust.effective(SKILL)
        self.assertEqual(t, "quarantine")
        self.assertIn("needs a new review", why)

    def test_not_runnable_is_na(self):
        from garage import trust
        self.assertEqual(trust.tier(DOCS), "n/a")
        self.assertTrue(trust.allowed(DOCS, True)[0])

    def test_update_refuses_trusted(self):
        from garage import trust
        rec = dict(reviewed(), trust="trusted", approved_by="owner", approved="2026-10-29", approval=1)
        with self.assertRaises(PermissionError):
            trust.put(SKILL, rec, "test")
        trust.put(SKILL, reviewed(), "test")
        self.assertEqual(trust.tier(SKILL), "reviewed")

    def test_reset(self):
        from garage import trust
        self.write_registry({SKILL: reviewed()})
        trust.reset(SKILL, "pin moved to " + SHA2[:12])
        self.assertEqual(trust.record(SKILL)["trust"], "quarantine")
        self.assertTrue(trust.record(SKILL)["history"])


class TestPolicy(GarageCase):
    def check(self, reg, pins=None):
        from garage import catalog, policy
        return policy.check(catalog.load(), pins if pins is not None else PINS, reg)

    def test_gpl_vendor_rejected_mit_ok(self):
        errs = self.check({})
        self.assertTrue(any(e.startswith(GPL_VENDOR) and "copyleft" in e for e in errs), errs)
        self.assertFalse(any(e.startswith(MIT_VENDOR) for e in errs), errs)

    def test_licence_classes(self):
        from garage.policy import licence_problem
        for bad in ("GPL-3.0", "AGPL-3.0-only", "LGPL-2.1", "none", "NOASSERTION", "", "BUSL-1.1", "SSPL-1.0",
                    "FSL-1.1-MIT", "Elastic-2.0", "LicenseRef-Commons-Clause", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0",
                    "PolyForm-Noncommercial-1.0.0", "source-available"):
            self.assertTrue(licence_problem(bad), bad)
        for ok in ("MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "MPL-2.0", "Unlicense", "CC-BY-4.0", "CC-BY-SA-4.0",
                   "0BSD", "CC0-1.0"):
            self.assertIsNone(licence_problem(ok), ok)

    def test_never_vendor(self):
        from garage.policy import never_vendor
        self.assertTrue(never_vendor("https://github.com/semgrep/semgrep-rules"))
        self.assertTrue(never_vendor("https://github.com/hacktricks-wiki/hacktricks"))
        self.assertTrue(never_vendor("https://book.hacktricks.wiki/en/index.html"))
        self.assertTrue(never_vendor("https://github.com/anthropics/skills/tree/main/skills/docx"))
        self.assertTrue(never_vendor("https://github.com/anthropics/skills/tree/main/skills/pdf"))
        self.assertIsNone(never_vendor("https://github.com/anthropics/skills/tree/main/skills/skill-creator"))

    def test_trusted_without_approval_rejected(self):
        errs = self.check({SKILL: dict(reviewed(), trust="trusted")})
        self.assertTrue(any("trusted without approved_by: owner" in e for e in errs), errs)
        self.assertTrue(any("approval id" in e for e in errs), errs)
        ok = self.check({SKILL: dict(reviewed(), trust="trusted", approved_by="owner", approved="2026-10-29",
                                     approval=7)})
        self.assertFalse([e for e in ok if e.startswith(SKILL)], ok)

    def test_sha_must_equal_pin(self):
        errs = self.check({SKILL: reviewed(sha=SHA2)})
        self.assertTrue(any("the pin is" in e for e in errs), errs)
        quarantined = {SKILL: {"trust": "quarantine", "sha": SHA2, "reasons": ["old"]}}
        self.assertFalse([e for e in self.check(quarantined) if e.startswith(SKILL)])

    def test_failed_scan_needs_waiver(self):
        errs = self.check({SKILL: reviewed(result="fail")})
        self.assertTrue(any("aguara failed" in e for e in errs), errs)
        rec = dict(reviewed(result="fail"), waivers=[{"tool": "aguara", "reason": "README.md:3 is docs"}])
        self.assertFalse([e for e in self.check({SKILL: rec}) if e.startswith(SKILL)])

    def test_record_for_unknown_or_non_runnable(self):
        errs = self.check({"https://github.com/x/y": reviewed(), DOCS: reviewed()})
        self.assertTrue(any("isn't in the catalog" in e for e in errs), errs)
        self.assertTrue(any("isn't runnable" in e for e in errs), errs)

    def test_bad_shape(self):
        errs = self.check({SKILL: {"trust": "golden", "sha": "abc"}})
        self.assertTrue(any("trust must be one of" in e for e in errs))
        self.assertTrue(any("40-hex" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
