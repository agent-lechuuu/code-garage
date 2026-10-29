"""Trust write-back (garage.trustgit): a review commits trust/registry.yaml only, as garage, and pushes; a rejected
push rebases, a conflicting one is replayed on upstream's registry; a --src copy only warns; garage-sync's pull keeps
local trust commits. A local bare repository stands in for GitHub: nothing is pushed anywhere else."""
import io
import json
import os
import re
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml
from helpers import ROOT, SHA, SHA2, SKILL, GarageCase, MIT_VENDOR, reviewed

GENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def fake_report():
    tools = ["skillspector", "aguara", "gitleaks", "mcp-scanner", "garage-checks"]
    return {"rid": SKILL, "sha": SHA, "date": "2026-10-29", "kind": "skill", "complete": True, "missing": [],
            "result": "pass", "target": "/x", "capabilities": {"shell": True, "network": False, "files": False,
                                                               "secrets": False},
            "scanners": [{"tool": t, "version": "1", "result": "pass", "findings": 0, "details": [], "note": ""}
                         for t in tools]}


class TrustGit(GarageCase):
    def setUp(self):
        super().setUp()
        self._genv = {k: os.environ.get(k) for k in GENV}
        os.environ.update(GENV)
        self.bare = self.tmp / "github.git"
        self.g("init", "-q", "--bare", "-b", "main", str(self.bare), cwd=self.tmp)
        self.g("init", "-q", "-b", "main", cwd=self.repo)
        self.g("add", "-A", cwd=self.repo)
        self.g("commit", "-q", "-m", "initial", cwd=self.repo)
        self.g("remote", "add", "origin", str(self.bare), cwd=self.repo)
        self.g("push", "-q", "-u", "origin", "main", cwd=self.repo)
        self.other = self.tmp / "other"          # someone else's clone (the coordinator merging a PR)
        self.g("clone", "-q", str(self.bare), str(self.other), cwd=self.tmp)

    def tearDown(self):
        for k, v in self._genv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def g(self, *args, cwd=None):
        p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd or self.repo,
                           capture_output=True, text=True, env=dict(os.environ, **GENV))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.rstrip()

    def upstream(self, rel, text, msg="upstream change"):
        f = self.other / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        self.g("add", rel, cwd=self.other)
        self.g("commit", "-q", "-m", msg, cwd=self.other)
        self.g("push", "-q", "origin", "main", cwd=self.other)

    def review(self):
        from garage import pins, review
        with redirect_stderr(io.StringIO()) as err:
            rec = review.record_review(SKILL, "reviewed", "tester", "C1-C25 ok", fake_report(), pins.get(SKILL))
        return rec, err.getvalue()

    def remote_registry(self):
        return yaml.safe_load(self.g("show", "main:trust/registry.yaml", cwd=self.bare)) or {}

    # ---------------------------------------------------------------------------------------------------------------
    def test_review_commits_only_the_registry_and_pushes(self):
        (self.repo / "catalog" / "test.yaml").write_text("# a local edit nobody committed\n")
        (self.repo / "notes.txt").write_text("staged, not ours\n")
        self.g("add", "notes.txt")
        rec, err = self.review()
        self.assertEqual(rec["trust"], "reviewed")
        self.assertEqual(err, "")
        log = self.g("log", "-1", "--format=%an <%ae>|%s", "main", cwd=self.bare)
        self.assertEqual(log, f"garage <garage@localhost>|trust: {SKILL} → reviewed (tester)")
        self.assertEqual(self.g("show", "--name-only", "--format=", "main", cwd=self.bare), "trust/registry.yaml")
        self.assertEqual(self.remote_registry()[SKILL]["trust"], "reviewed")
        status = self.g("status", "--porcelain")
        self.assertIn(" M catalog/test.yaml", status)       # untouched, still uncommitted
        self.assertIn("A  notes.txt", status)               # still staged, not committed
        self.assertNotIn("registry.yaml", status)

    def test_rejected_push_rebases(self):
        self.upstream("docs/new.md", "merged elsewhere\n")
        (self.repo / "catalog" / "test.yaml").write_text("# local edit\n")
        self.review()
        subjects = self.g("log", "--format=%s", "main", cwd=self.bare).split("\n")
        self.assertEqual(subjects[:2], [f"trust: {SKILL} → reviewed (tester)", "upstream change"])
        self.assertTrue((self.repo / "docs" / "new.md").is_file())
        self.assertEqual((self.repo / "catalog" / "test.yaml").read_text(), "# local edit\n")   # autostash
        self.assertEqual(self.g("rev-parse", "HEAD"), self.g("rev-parse", "main", cwd=self.bare))

    def test_conflict_is_replayed_on_upstream_registry(self):
        from garage import trust
        other = {MIT_VENDOR: {"trust": "quarantine", "sha": SHA, "reasons": ["upstream review"]}}
        self.upstream("trust/registry.yaml", trust._dump(other), "trust: upstream record")
        self.review()
        reg = self.remote_registry()
        self.assertEqual(reg[SKILL]["trust"], "reviewed")                 # ours
        self.assertEqual(reg[MIT_VENDOR]["reasons"], ["upstream review"])  # theirs, kept
        self.assertEqual(self.g("rev-parse", "HEAD"), self.g("rev-parse", "main", cwd=self.bare))
        self.assertEqual([s for s in self.g("status", "--porcelain").splitlines() if "registry.lock" not in s], [])
        self.assertFalse((self.repo / ".git" / "rebase-merge").exists())

    def test_replay_skips_a_record_whose_pin_moved_upstream(self):
        from garage import trust
        pins = yaml.safe_load((self.repo / "lock" / "pins.yaml").read_text())
        pins[SKILL]["sha"] = SHA2
        (self.other / "lock" / "pins.yaml").write_text(yaml.safe_dump(pins))
        self.g("add", "lock/pins.yaml", cwd=self.other)
        reset = {SKILL: {"trust": "quarantine", "sha": SHA, "reasons": ["pin moved"]}}
        self.upstream("trust/registry.yaml", trust._dump(reset), "pin bump")
        _, err = self.review()
        self.assertIn("upstream moved the pin", err)
        self.assertEqual(self.remote_registry()[SKILL]["reasons"], ["pin moved"])   # upstream's reset won
        self.assertEqual(self.g("rev-parse", "HEAD"), self.g("rev-parse", "main", cwd=self.bare))
        self.assertEqual(trust.record(SKILL)["reasons"], ["pin moved"])

    def test_no_upstream_and_unreachable_remote_keep_the_commit(self):
        self.g("remote", "set-url", "origin", str(self.tmp / "gone.git"))
        _, err = self.review()
        self.assertIn("committed locally", err)
        self.assertEqual(self.g("log", "-1", "--format=%s"), f"trust: {SKILL} → reviewed (tester)")

    def test_not_a_clone_warns(self):
        import shutil
        shutil.rmtree(self.repo / ".git")
        rec, err = self.review()
        self.assertEqual(rec["trust"], "reviewed")
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("is not a git clone", err)
        self.assertIn("isn't in git", err)

    def test_promote_dry_run_writes_and_commits_nothing(self):
        from garage import promote
        self.write_registry({SKILL: reviewed()})
        self.g("commit", "-q", "-am", "registry")
        before = self.g("rev-parse", "HEAD")
        os.environ["GARAGE_LECHU_ASK"] = "/nonexistent/lechu-ask"
        self.addCleanup(os.environ.pop, "GARAGE_LECHU_ASK", None)
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            self.assertEqual(promote.main(["--propose", "--dry-run", "--json"]), 0)
        self.assertFalse(json.loads(out.getvalue())["sent"])
        self.assertEqual(self.g("rev-parse", "HEAD"), before)
        self.assertEqual([s for s in self.g("status", "--porcelain").splitlines() if "registry.lock" not in s], [])

    def test_trusted_publish_message(self):
        from garage import trustgit
        self.assertEqual(trustgit.message([SKILL], "trusted", "owner, approval #41"),
                         f"trust: {SKILL} → trusted (owner, approval #41)")
        self.assertTrue(trustgit.message([SKILL, MIT_VENDOR], "trusted", "owner").startswith("trust: 2 items → trusted"))

    def test_garage_sync_pull_keeps_local_trust_commits(self):
        unit = (ROOT / "infra" / "systemd" / "garage-sync.service").read_text()
        line = next(ln for ln in unit.splitlines() if ln.startswith("ExecStart=/bin/sh -c "))
        script = re.match(r"ExecStart=/bin/sh -c '(.*)'$", line).group(1).replace("/data/apps/garage/repo",
                                                                                   str(self.repo))
        self.assertIn("--rebase --autostash", script)
        self.assertNotRegex(unit, r"reset --hard|checkout -- |--force|clean -f")
        self.g("remote", "set-url", "origin", str(self.tmp / "gone.git"))
        self.review()                                       # a trust commit that could not be pushed
        self.g("remote", "set-url", "origin", str(self.bare))
        mine = (self.repo / "trust" / "registry.yaml").read_text()
        self.upstream("catalog/extra.md", "new upstream file\n")
        (self.repo / "catalog" / "test.yaml").write_text((self.repo / "catalog" / "test.yaml").read_text() + "\n")
        p = subprocess.run(["sh", "-c", script], capture_output=True, text=True, env=dict(os.environ, **GENV))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((self.repo / "trust" / "registry.yaml").read_text(), mine)
        self.assertTrue((self.repo / "catalog" / "extra.md").is_file())
        self.assertIn(" M catalog/test.yaml", self.g("status", "--porcelain"))
        self.assertEqual(self.g("log", "-1", "--format=%s"), f"trust: {SKILL} → reviewed (tester)")
        # a conflicting upstream registry: the pull fails loudly, the local commit and file stay as they were
        from garage import trust
        self.upstream("trust/registry.yaml", trust._dump({MIT_VENDOR: {"trust": "quarantine", "sha": SHA}}))
        p = subprocess.run(["sh", "-c", script], capture_output=True, text=True, env=dict(os.environ, **GENV))
        self.assertEqual(p.returncode, 1)
        self.assertEqual((self.repo / "trust" / "registry.yaml").read_text(), mine)
        self.assertFalse((self.repo / ".git" / "rebase-merge").exists())
