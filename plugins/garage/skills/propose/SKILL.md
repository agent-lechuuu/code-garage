---
name: propose
description: Suggest a new resource for the Code Garage when you found or used something good that it lacks.
---

# Propose an addition

When a search came up empty and you found a good existing repo, skill, MCP server or template elsewhere, or a garage
entry is wrong (moved, archived, better alternative), propose it so the next agent finds it.

1. Check it isn't there: `garage search "..."` and `garage show URL`.
2. Pick the existing topic it belongs to (`garage search WORDS`, `garage show TOPIC_ID`); unknown topic ids are
   refused. If none fits, pick the closest and say so in `--why`.
3. Dry run first: `garage propose URL --topic TOPIC_ID --why "one line: when to pick it" --dry-run`.
   It checks the repo (licence, stars, last push, archived) and shows the proposal file.
4. Then the same command without `--dry-run`. It writes `proposals/<date>-<slug>.yaml` and opens a pull request.
   On a server with an approval broker the push may wait for the owner's approval; don't retry or work around it.

Prefer maintained (pushed in the last 12-18 months), permissively licensed, widely used items. A proposal enters as
`quarantine` and is reviewed before anyone may load it.

## Trust
- `quarantine`: read only (`garage show`, `garage grep`); never add, install or run it.
- `reviewed`: OK in interactive sessions; tell the user it is "reviewed, not yet trusted".
- `trusted`: OK in unattended runs too.
- `GARAGE_UNATTENDED=1` (scheduled jobs, the assistant): use `trusted` items only.
