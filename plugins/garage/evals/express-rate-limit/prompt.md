---
max_turns: 30
timeout_seconds: 480
tags: [build, backend]
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Write, Edit, mcp__plugin_garage_garage__search, mcp__plugin_garage_garage__show, mcp__plugin_garage_garage__recipe, mcp__plugin_garage_garage__grep]
---

Add rate limiting to this Express API: at most 100 requests per 15 minutes per client IP on the /api routes, answering 429 with a JSON error.
