"""garage review gate, the job's inbox, and garage promote (dry-run card; approval checked with a fake broker)."""
import io
import json
import os
import stat
from contextlib import redirect_stdout

from helpers import FIXTURES, SHA, SKILL, GarageCase, reviewed


def fake_report(result="pass", complete=True):
    tools = ["skillspector", "aguara", "gitleaks", "mcp-scanner", "garage-checks"]
    return {"rid": SKILL, "sha": SHA, "date": "2026-10-29", "kind": "skill", "complete": complete,
            "missing": [] if complete else ["skillspector"], "result": result, "target": "/x",
            "capabilities": {"shell": True, "network": False, "files": False, "secrets": False},
            "scanners": [{"tool": t, "version": "1", "result": (result if t == "aguara" else "pass"), "findings": 1,
                          "details": [{"rule": "R1", "file": "README.md", "line": 3}], "note": ""} for t in tools]}


class TestReview(GarageCase):
    def pin(self):
        from garage import pins
        return pins.get(SKILL)

    def test_reviewed_when_clean(self):
        from garage import review, trust
        rec = review.record_review(SKILL, "reviewed", "tester", "C1-C25 ok", fake_report(), self.pin(), "tidy")
        self.assertEqual(rec["trust"], "reviewed")
        self.assertEqual(trust.tier(SKILL), "reviewed")
        self.assertTrue(review.review_file(SKILL, SHA).is_file())

    def test_failed_scanner_needs_waiver(self):
        from garage import review
        rec = review.record_review(SKILL, "reviewed", "tester", "notes", fake_report("fail"), self.pin())
        self.assertEqual(rec["trust"], "quarantine")
        self.assertIn("aguara failed", " ".join(rec["reasons"]))
        rec = review.record_review(SKILL, "reviewed", "tester", "notes", fake_report("fail"), self.pin(),
                                   waivers=[{"tool": "aguara", "reason": "README.md:3 documents an installer"}])
        self.assertEqual(rec["trust"], "reviewed")

    def test_unattended_cannot_waive(self):
        from garage import review
        rec = review.record_review(SKILL, "reviewed", "job", "notes", fake_report("fail"), self.pin(),
                                   waivers=[{"tool": "aguara", "reason": "x"}], unattended=True)
        self.assertEqual(rec["trust"], "quarantine")
        self.assertIn("interactive reviewer", " ".join(rec["reasons"]))

    def test_incomplete_scan_and_checklist_fail(self):
        from garage import review
        rec = review.record_review(SKILL, "reviewed", "t", "n", fake_report(complete=False), self.pin())
        self.assertEqual(rec["trust"], "quarantine")
        rec = review.record_review(SKILL, "reviewed", "t", "n", fake_report(), self.pin(),
                                   checklist={"C11": "fail: SKILL.md:12 pipes curl into sh"})
        self.assertEqual(rec["trust"], "quarantine")

    def test_review_never_writes_trusted(self):
        from garage import review
        with self.assertRaises(ValueError):
            review.record_review(SKILL, "trusted", "t", "n", fake_report(), self.pin())

    def test_ingest_from_inbox(self):
        from garage import review, scan, trust
        self.snapshot(SKILL, FIXTURES / "clean-skill")
        rep = fake_report()
        f = scan.report_file(SKILL, SHA)
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps(rep))
        self.assertEqual(review.main(["--check"]), 0)
        verdict = {"rid": SKILL, "sha": SHA, "verdict": "reviewed", "summary": "tidy commit messages",
                   "can": {"shell": True, "network": False, "files": False, "secrets": False},
                   "checklist": {f"C{i}": "ok" for i in range(1, 26)}, "notes": "read SKILL.md"}
        review.inbox().mkdir(parents=True)
        (review.inbox() / "a.json").write_text(json.dumps(verdict))
        (review.inbox() / "b.json").write_text(json.dumps(dict(verdict, sha="c" * 40)))
        with redirect_stdout(io.StringIO()) as out:
            review.main(["--ingest"])
        self.assertIn("rejected", out.getvalue())
        self.assertEqual(trust.tier(SKILL), "reviewed")
        self.assertEqual(trust.record(SKILL)["reviewed_by"], review.JOB_REVIEWER)
        self.assertEqual(review.main(["--check"]), 1)


class TestPromote(GarageCase):
    def fake_ask(self, decision="approved", kind="garage.promote", fp=None):
        """A stand-in for lechu-ask: asks get id 41; --status 41 reports the given decision for the given card."""
        state = self.tmp / "ask.json"
        script = self.tmp / "lechu-ask"
        script.write_text(f"""#!/usr/bin/python3 -I
import json, sys
st = {str(state)!r}
a = sys.argv[1:]
if a[0] == "--status":
    print(json.dumps(json.load(open(st))))
else:
    cmd = a[a.index("--command") + 1]
    if {fp!r}:
        cmd = cmd.rsplit("garage set ", 1)[0] + "garage set " + {fp!r}
    json.dump({{"id": 41, "kind": {kind!r}, "command": cmd, "decision": {decision!r}}}, open(st, "w"))
    print(json.dumps({{"id": 41, "decision": {decision!r}, "note": ""}}))
""")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        os.environ["GARAGE_LECHU_ASK"] = str(script)
        self.addCleanup(os.environ.pop, "GARAGE_LECHU_ASK", None)

    def test_dry_run_sends_nothing(self):
        from garage import promote, trust
        self.write_registry({SKILL: reviewed()})
        os.environ["GARAGE_LECHU_ASK"] = "/nonexistent/lechu-ask"
        self.addCleanup(os.environ.pop, "GARAGE_LECHU_ASK", None)
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(promote.main(["--propose", "--dry-run", "--json"]), 0)
        card = json.loads(out.getvalue())
        self.assertFalse(card["sent"])
        self.assertIn("tidy", card["card"])
        self.assertIn("Can: shell", card["card"])
        self.assertEqual(trust.tier(SKILL), "reviewed")

    def test_approval_makes_trusted(self):
        from garage import promote, trust
        self.write_registry({SKILL: reviewed()})
        self.fake_ask("approved")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(promote.main(["--propose"]), 0)
        rec = trust.record(SKILL)
        self.assertEqual((rec["trust"], rec["approved_by"], rec["approval"]), ("trusted", "owner", 41))
        self.assertTrue(trust.allowed(SKILL, True)[0])

    def test_denied_stays_reviewed(self):
        from garage import promote, trust
        self.write_registry({SKILL: reviewed()})
        self.fake_ask("denied")
        with redirect_stdout(io.StringIO()):
            promote.main(["--propose"])
        self.assertEqual(trust.tier(SKILL), "reviewed")

    def test_other_kind_or_other_card_refused(self):
        from garage import promote, trust
        self.write_registry({SKILL: reviewed()})
        self.fake_ask("approved", kind="git.push_elsewhere")
        with redirect_stdout(io.StringIO()):
            promote.main(["--propose"])
        self.assertEqual(trust.tier(SKILL), "reviewed")
        self.fake_ask("approved", fp="0123456789abcdef")
        with redirect_stdout(io.StringIO()):
            promote.main(["--propose"])
        self.assertEqual(trust.tier(SKILL), "reviewed")
