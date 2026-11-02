---
max_turns: 30
timeout_seconds: 480
tags: [build, backend]
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Write, Edit, mcp__plugin_garage_garage__search, mcp__plugin_garage_garage__show, mcp__plugin_garage_garage__recipe, mcp__plugin_garage_garage__grep]
---

Add retries with exponential backoff and jitter to the HTTP calls in client.py: retry on connection errors and 5xx answers, at most 5 attempts.
