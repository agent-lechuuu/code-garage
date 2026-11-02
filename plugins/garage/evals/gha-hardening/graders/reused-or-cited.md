---
type: llm
focus: last_message
---

The task was a coding request in a project where the Code Garage plugin (a curated catalog of existing code) may be
available. Judge only the final reply.

PASS if the reply names at least one specific existing item that it says came from the Code Garage (the "garage"):
a package, repo, snippet, skill, MCP server, template or practice list, by name and/or garage id, and says it was
reused, installed, adapted, vendored or followed (or explains why the garage item was only read). The item must fit
the task: for example a GitHub Actions hardening skill or guide, zizmor, harden-runner, pinned actions or a GitHub Actions security practice list.

FAIL if the reply does not mention the Code Garage or a garage id at all, or mentions it without naming any item.
