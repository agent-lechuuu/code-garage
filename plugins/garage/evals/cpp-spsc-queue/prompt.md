---
max_turns: 30
timeout_seconds: 480
tags: [build, systems]
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Write, Edit, mcp__plugin_garage_garage__search, mcp__plugin_garage_garage__show, mcp__plugin_garage_garage__recipe, mcp__plugin_garage_garage__grep]
---

I need a lock-free SPSC queue for this C++ service: the capture thread pushes frames and the encoder thread pops them. Replace the mutex-protected queue in src/main.cpp with it.
