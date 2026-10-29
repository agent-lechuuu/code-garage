---
name: use
description: Add, scaffold or install an item found in the Code Garage (garage add, skill add, new), keeping its licence and citing its id.
---

# Use a garage item

Check the tier first (`garage show ID` prints it first; the MCP tool `recipe ID` gives the exact steps and whether
this session may use it). Then, by kind of item:

| Item | Command | What it does |
|---|---|---|
| package (`use: install`) | the `install` line, e.g. `npm install x` | a normal dependency; nothing copied |
| code to copy (`use: vendor`, snippet) | `garage add ID --into vendor/` | copies the pinned snapshot with LICENSE/NOTICE, writes `vendor/<name>/.garage.json` |
| agent skill | `garage skill add ID` | copies it into `.claude/skills/<name>/` with its LICENSE; loads next session |
| project template | `garage new NAME --template ID` | scaffolds at the pinned commit, writes `CLAUDE.md` |
| MCP server | `garage add ID --into vendor/`, then read its README and register it yourself (`claude mcp add`) | garage copies never ship `.mcp.json` or hooks |
| reference | read `url` or `local_path` | learn from it; don't paste it |

Rules:
- Keep the licence: never delete LICENSE, NOTICE or copyright headers; mark files you change ("changed by ...").
  GPL/AGPL: dependency or separate process only, never copy its code. No licence: read and link only.
- Don't edit `.garage.json`; it records url, sha and licence for the next person.
- Cite the garage id in the commit message: `garage:<topic id or url>`.
- With little to no modification is the point: adapt with config and thin glue, not rewrites.

## Trust
- `quarantine`: read only (`garage show`, `garage grep`); never add, install or run it.
- `reviewed`: OK in interactive sessions; tell the user it is "reviewed, not yet trusted".
- `trusted`: OK in unattended runs too.
- `GARAGE_UNATTENDED=1` (scheduled jobs, the assistant): use `trusted` items only.
