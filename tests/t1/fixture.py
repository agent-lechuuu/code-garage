"""A tiny garage for the T1 tests: a repo with two slices, synonyms and the real schema, in a temporary folder."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

FRONTEND = """\
slice: frontend
generated: 2026-10-28
topics:
  - id: frontend.components.headless
    title: Headless UI components
    area: components
    why: Accessible dialogs, menus and popovers without styling, for React apps.
    practices:
      - text: Use a tested primitive for focus management; never hand-roll a focus trap.
        source: https://example.org/focus
    resources:
      - name: Radix Primitives
        url: https://github.com/radix-ui/primitives
        kind: repo
        license: MIT
        stars: 17000
        tier: 1
        use: install
        install: npm install @radix-ui/react-dialog
        note: Unstyled accessible React primitives (dialog, popover, menu).
      - name: Headless UI
        url: https://github.com/tailwindlabs/headlessui
        kind: repo
        license: MIT
        stars: 27000
        tier: 2
        use: install
        note: From the Tailwind team; fewer components.
    see_also: [frontend.forms.validation]
  - id: frontend.forms.validation
    title: Form validation
    area: forms
    why: Validate form input on the client with a schema shared with the server.
    resources:
      - name: zod
        url: https://www.npmjs.com/package/zod
        kind: tool
        license: MIT
        tier: 1
        use: install
        note: TypeScript-first schema validation.
      - name: Form starter template
        url: https://github.com/example/form-starter
        kind: template
        license: MIT
        tier: 2
        use: template
        note: A starter project with forms wired up.
  - id: frontend.agent.skills
    title: Frontend agent skills
    area: agent
    why: Skills that teach an agent frontend design rules.
    resources:
      - name: frontend-design skill
        url: https://github.com/example/skills/tree/HEAD/skills/frontend-design
        kind: skill
        license: Apache-2.0
        tier: 1
        use: skill
        path: skills/frontend-design
        note: Design rules for distinctive interfaces; no shell, no network.
"""

BACKEND = """\
slice: backend
generated: 2026-10-27
topics:
  - id: backend.auth.sessions
    title: Sessions and login
    area: auth
    why: Cookie sessions, login flows and authentication for web backends.
    resources:
      - name: Lucia guide
        url: https://lucia-auth.com/
        kind: guide
        license: CC0-1.0
        tier: 1
        use: reference
        note: How to implement session authentication from scratch.
      - name: GPL session server
        url: https://github.com/example/gpl-sessions.git
        kind: repo
        license: GPL-3.0
        stars: 300
        tier: 3
        use: reference
        note: A copyleft reference implementation of sessions.
    see_also: [frontend.forms.validation]
  - id: backend.jobs.queues
    title: Background job queues
    area: jobs
    why: Run work outside the request with retries and scheduling.
    resources:
      - name: BullMQ
        url: https://github.com/taskforcesh/bullmq
        kind: repo
        license: MIT
        stars: 7000
        tier: 1
        use: install
        note: Redis-backed queue for Node.
"""

SYNONYMS = """\
synonyms:
  auth: [authentication, login, session]
  modal: [dialog, popover]
"""


class Garage:
    """with Garage() as g: g.repo, g.home (env GARAGE_REPO / GARAGE_HOME set while inside)."""

    def __init__(self, extra=None):
        self.extra = extra or {}

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="garage-t1-"))
        self.repo, self.home = self.tmp / "repo", self.tmp / "home"
        (self.repo / "catalog").mkdir(parents=True)
        (self.repo / "schema").mkdir()
        self.home.mkdir()
        shutil.copy(ROOT / "schema" / "catalog.schema.json", self.repo / "schema")
        files = {"catalog/frontend.yaml": FRONTEND, "catalog/backend.yaml": BACKEND, "catalog/synonyms.yaml": SYNONYMS}
        files.update(self.extra)
        for rel, text in files.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text)
        self.old = {k: os.environ.get(k) for k in ("GARAGE_REPO", "GARAGE_HOME", "GARAGE_UNATTENDED")}
        os.environ["GARAGE_REPO"], os.environ["GARAGE_HOME"] = str(self.repo), str(self.home)
        os.environ.pop("GARAGE_UNATTENDED", None)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)


def fake_optional(**mods):
    """A stand-in for garage.optional: returns the given fake modules, None for everything else."""
    return lambda name: mods.get(name)
