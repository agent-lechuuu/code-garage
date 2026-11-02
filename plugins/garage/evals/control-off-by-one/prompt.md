---
max_turns: 12
timeout_seconds: 480
tags: [control]
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Write, Edit, mcp__plugin_garage_garage__search, mcp__plugin_garage_garage__show, mcp__plugin_garage_garage__recipe, mcp__plugin_garage_garage__grep]
---

Fix the off-by-one bug in paginate() in pagination.py: the last page is dropped.
