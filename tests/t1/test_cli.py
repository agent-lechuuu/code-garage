"""T1: the CLI (subprocess, --json) and add / skill / new / propose against fake mirror and trust modules."""
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import fixture
from garage import add, index, new, propose, skill

SKILL_MD = "---\nname: frontend-design\ndescription: Design rules.\n---\nBe bold.\n"


def fake_mirror(fetched):
    """mirror.fetch(rid, dest): a snapshot with LICENSE + .garage.json; a skill repo holds skills/<name>/SKILL.md."""
    def fetch(rid, dest):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "LICENSE").write_text("MIT\n")
        (dest / ".garage.json").write_text(json.dumps({"rid": rid, "sha": "a" * 40}))
        if "skills" in rid:
            (dest / "SKILL.md").write_text(SKILL_MD)
        else:
            (dest / "README.md").write_text("template\n")
            (dest / "CLAUDE.md").write_text("# From the template\n")
        fetched.append((rid, str(dest)))
        return str(dest)
    return types.SimpleNamespace(fetch=fetch, local_path=lambda rid: None)


def fake_trust(tier):
    def allowed(rid, unattended):
        if tier == "trusted" or (tier == "reviewed" and not unattended):
            return True, tier
        return False, f"{tier}: not allowed{' unattended' if unattended else ''}"
    return types.SimpleNamespace(allowed=allowed, tier=lambda rid: tier)


class Cli(unittest.TestCase):
    def garage(self, *args, env=None):
        e = dict(os.environ, GARAGE_REPO=str(self.g.repo), GARAGE_HOME=str(self.g.home), **(env or {}))
        p = subprocess.run([sys.executable, "-I", str(fixture.ROOT / "tools" / "garage"), *args], capture_output=True,
                           text=True, env=e, timeout=60)
        return p.returncode, p.stdout, p.stderr

    def setUp(self):
        self.g = fixture.Garage().__enter__()

    def tearDown(self):
        self.g.__exit__(None, None, None)

    def test_search_show_json(self):
        rc, out, err = self.garage("search", "--json", "headless", "dialog")
        self.assertEqual(rc, 0, err)
        r = json.loads(out)
        self.assertEqual(r[0]["id"], "frontend.components.headless")
        rc, out, _ = self.garage("show", "--json", "zod")
        self.assertEqual(json.loads(out)["install"], "npm install zod")
        rc, out, _ = self.garage("show", "nothing-here")
        self.assertEqual(rc, 1)
        rc, out, _ = self.garage("search", "headless")
        self.assertIn("best: Headless UI <https://github.com/tailwindlabs/headlessui>", out)

    def test_validate_build_index(self):
        rc, out, err = self.garage("validate", "--json")
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(json.loads(out)["ok"])
        self.assertEqual(self.garage("build", "--check")[0], 1)   # nothing generated yet
        self.assertEqual(self.garage("build")[0], 0)
        rc, out, _ = self.garage("build", "--check", "--json")
        self.assertEqual((rc, json.loads(out)["stale"]), (0, []))
        self.assertTrue((self.g.repo / "INDEX.md").is_file() and (self.g.repo / "dist" / "catalog.json").is_file())
        md = (self.g.repo / "dist" / "index" / "frontend.md").read_text()
        self.assertIn("[Radix Primitives](https://github.com/radix-ui/primitives) · MIT · 17k★ · t1 · install", md)
        dist = json.loads((self.g.repo / "dist" / "catalog.json").read_text())
        self.assertEqual(set(dist), {"version", "generated", "topics", "resources", "trust_registry", "synonyms"})
        rc, out, _ = self.garage("index", "--json")
        self.assertEqual(json.loads(out)["topics"], 5)

    def test_doctor_and_delegation(self):
        rc, out, _ = self.garage("doctor", "--json")
        mods = {x["module"] for x in json.loads(out)}
        self.assertTrue({"paths", "catalog", "search", "index"} <= mods)
        rc, out, err = self.garage("validate", "--guard", str(self.g.repo / "catalog" / "frontend.yaml"))
        self.assertEqual(rc, 0, out)

    def test_propose_dry_run(self):
        rc, out, err = self.garage("propose", "https://github.com/example/new-thing", "--topic",
                                   "frontend.forms.validation", "--why", "A better validator for agents.",
                                   "--dry-run", "--json")
        self.assertEqual(rc, 0, err)
        r = json.loads(out)
        self.assertTrue(r["dry_run"])
        self.assertTrue(r["path"].endswith("-example-new-thing.yaml"))
        self.assertFalse((self.g.repo / "proposals").exists())   # dry run writes nothing
        rc, out, err = self.garage("propose", "https://github.com/taskforcesh/bullmq", "--topic",
                                   "backend.jobs.queues", "--why", "Already there, should be refused.", "--dry-run")
        self.assertEqual(rc, 1)
        self.assertIn("already in the catalog", err)
        rc, out, err = self.garage("propose", "https://github.com/example/other", "--topic", "nope.nope", "--why",
                                   "A topic that does not exist is refused.", "--dry-run")
        self.assertEqual(rc, 1)
        self.assertIn("unknown topic", err)
        rc, out, err = self.garage("propose", "https://github.com/example/new-thing", "--topic",
                                   "frontend.forms.validation", "--why", "A better validator for agents.", "--dry-run")
        self.assertEqual(rc, 0, err)
        self.assertIn("url: https://github.com/example/new-thing", out)   # the proposal itself
        self.assertIn("(dry run: would write ", out)                       # and where it would go


class AddSkillNew(unittest.TestCase):
    def setUp(self):
        self.g = fixture.Garage().__enter__()
        self.work = Path(tempfile.mkdtemp(prefix="garage-proj-"))
        self.fetched = []
        self.p = []

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.g.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.work, ignore_errors=True)

    def mods(self, **m):
        for mod in (add, index):
            p = mock.patch.object(mod, "optional", fixture.fake_optional(**m))
            p.start()
            self.p.append(p)

    def test_install_and_reference_items_are_not_copied(self):
        self.mods()
        r = add.add("frontend.components.headless")   # topic: no runnable resource -> the first one, an install
        self.assertEqual((r["action"], r["install"]), ("install", "npm install @radix-ui/react-dialog"))
        r = add.add("https://lucia-auth.com")
        self.assertEqual(r["action"], "reference")
        self.assertEqual(add.add("nope")["action"], "unknown")

    def test_runnable_refused_without_trust_module(self):
        self.mods(mirror=fake_mirror(self.fetched))
        r = add.add("frontend.forms.validation", into=str(self.work / "vendor"))
        self.assertEqual(r["action"], "refused")
        self.assertIn("garage.trust is not installed", r["reason"])
        self.assertEqual(self.fetched, [])

    def test_trust_tiers(self):
        self.mods(mirror=fake_mirror(self.fetched), trust=fake_trust("quarantine"))
        self.assertEqual(add.add("frontend.forms.validation", into=str(self.work))["action"], "refused")
        for p in self.p:
            p.stop()
        self.p = []
        self.mods(mirror=fake_mirror(self.fetched), trust=fake_trust("reviewed"))
        with mock.patch.dict(os.environ, {"GARAGE_UNATTENDED": "1"}):
            self.assertEqual(add.add("frontend.forms.validation", into=str(self.work))["action"], "refused")
        r = add.add("frontend.forms.validation", into=str(self.work / "vendor"))
        self.assertEqual(r["action"], "copied", r)
        self.assertEqual(r["dest"], str(self.work / "vendor" / "form-starter"))
        self.assertEqual(self.fetched[0][0], "https://github.com/example/form-starter")
        again = add.add("frontend.forms.validation", into=str(self.work / "vendor"))
        self.assertEqual(again["action"], "refused")   # never overwrites

    def test_skill_add_list(self):
        self.mods(mirror=fake_mirror(self.fetched), trust=fake_trust("trusted"))
        r = skill.add("frontend.agent.skills", project=str(self.work))
        self.assertEqual(r["action"], "installed", r)
        d = self.work / ".claude" / "skills" / "frontend-design"
        self.assertTrue((d / "SKILL.md").is_file() and (d / "LICENSE").is_file())
        meta = json.loads((d / ".garage.json").read_text())
        self.assertEqual((meta["rid"], meta["skill"], meta["sha"]),
                         ("https://github.com/example/skills/tree/HEAD/skills/frontend-design", "frontend-design",
                          "a" * 40))
        self.assertEqual([x.name for x in (self.work / ".claude" / "skills").iterdir()], ["frontend-design"])
        self.assertEqual(skill.add("frontend.agent.skills", project=str(self.work))["action"], "refused")  # exists
        with mock.patch.object(skill.search, "trust_of", lambda res: "trusted"):
            listed = skill.list_skills(str(self.work))
        self.assertEqual((listed[0]["skill"], listed[0]["trust"]), ("frontend-design", "trusted"))
        self.assertEqual(skill.add("backend.jobs.queues", project=str(self.work))["action"], "refused")  # not a skill

    def test_skill_quarantine_refused(self):
        self.mods(mirror=fake_mirror(self.fetched), trust=fake_trust("quarantine"))
        r = skill.add("frontend.agent.skills", project=str(self.work))
        self.assertEqual(r["action"], "refused")
        self.assertFalse((self.work / ".claude").exists())

    def test_new(self):
        self.mods(mirror=fake_mirror(self.fetched), trust=fake_trust("reviewed"))
        r = new.new("plain", parent=str(self.work))
        self.assertTrue(r["ok"])
        text = (self.work / "plain" / "CLAUDE.md").read_text()
        self.assertIn("Search the garage before building anything", text)
        self.assertIn("Cite the garage id", text)
        r = new.new("app", template="frontend.forms.validation", parent=str(self.work))
        self.assertEqual(r["action"], "created", r)
        text = (self.work / "app" / "CLAUDE.md").read_text()
        self.assertTrue(text.startswith("# From the template") and "## Code Garage" in text)
        self.assertTrue((self.work / "app" / "LICENSE").is_file())
        self.assertEqual(new.new("app", parent=str(self.work))["action"], "refused")   # not empty
        r = new.new("bad", template="backend.jobs.queues", parent=str(self.work))     # not a template
        self.assertFalse(r["ok"])
        self.assertFalse((self.work / "bad").exists())

    def test_propose_writes_file(self):
        self.mods()
        out = self.work / "proposals"
        r = propose.propose("https://github.com/example/new-skill", "frontend.agent.skills",
                            "A skill that teaches accessible forms.", use="skill", kind="skill", out=str(out))
        self.assertTrue(r["ok"], r)
        import yaml
        data = yaml.safe_load(Path(r["path"]).read_text())
        self.assertEqual((data["resource"]["use"], data["trust"]), ("skill", "quarantine"))
        self.assertFalse(propose.propose("ftp://x", "a.b.c", "short")["ok"])


if __name__ == "__main__":
    unittest.main()
