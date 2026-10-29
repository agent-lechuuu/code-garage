# S7 `ai` — AI/ML engineering and the AI-agent toolbox (research report, 2026-10-28)

Catalog: `ai.yaml` — 105 topics, 439 resources (validated with the brief's command). ~350 GitHub repos verified live
with `ghmeta.py` today; every skill, plugin and MCP server listed had its SKILL.md / plugin.json / README read as data.
Priority was the agent toolbox (skills, Claude Code, MCP, context) = 54 topics; LLM apps 27; ML engineering 16; prompting 5; agent engineering 8.

## 1. Map of the slice (area → topics)

| area | topics | what is in it |
|---|---|---|
| skills | 10 | SKILL.md spec, anthropics/skills, skill-creator, workflow packs (superpowers, mattpocock), planning, document skills, frontend/testing skills, vendor packs, discovery (skills.sh), security skills + scanners |
| claude-code | 18 | docs/best practices, plugins + marketplaces, official dev-workflow plugins, subagents, commands, hooks, CLAUDE.md/memory, settings+sandboxing, statusline, output styles, LSP plugins, parallel/agent teams, headless+CI, usage/costs, guides+clients, mods, channels/goal/advisor, project setup |
| mcp | 15 | spec, SDKs (10 languages), building (FastMCP, mcp-builder), 7 live reference servers (+13 archived), registry, inspector/testing, packaging (MCPB, MCP Apps, tunnels), servers: docs, browser, code intelligence, GitHub, web search, databases (→S2), infra (→S4/S5), clients |
| context | 6 | AGENTS.md/Cursor/Copilot rules, llms.txt, context packers, codebase understanding, spec-driven dev kits, agent memory |
| agents | 8 | Anthropic design-guide series, harness education, sandboxes, multi-agent coding orchestration, OSS coding agents, coding-agent evals (SWE-bench, Terminal-Bench 2), protocols (A2A/AG-UI/ACP), computer use |
| prompting | 5 | Anthropic docs + model-specific guides, tutorials, DSPy/promptfoo optimization, system prompts, context engineering |
| llm-apps | 27 | Anthropic SDKs + `ant` CLI, Messages API features, server tools, Claude Agent SDK, Managed Agents, cookbooks, gateways, Python/TS frameworks, chat UI, RAG frameworks + components, document ingestion, OCR, structured validation, guardrails, evals, observability, tokens/cost, local inference (4 GB GPU), serving, CLI clients, STT, TTS/voice agents, web data, image generation, in-browser inference |
| ml | 16 | PyTorch stack, JAX, HF, fine-tuning, classical/tabular, time series, experiment tracking, pipelines/data versioning, serving/export, labelling, vision, notebooks, courses (foundations, applied), system design, datasets |

## 2. The 20 most valuable resources and why

1. **anthropics/skills** (184k★, Apache-2.0 per folder) — the reference SKILL.md implementations; skill-creator, mcp-builder, claude-api, frontend-design, webapp-testing are the ones agents here will load daily.
2. **obra/superpowers** (307k★, MIT) — the best process pack: brainstorming → writing-plans → TDD → systematic-debugging → verification-before-completion. Hook reviewed (injects its own using-superpowers skill, no network).
3. **mattpocock/skills** (305k★, MIT) — small composable engineering skills (tdd, triage, diagnosing-bugs, grill-me, handoff); #2 on skills.sh; also an official-marketplace plugin.
4. **anthropics/claude-plugins-official** (45k★, Apache-2.0) — 315 vetted plugins: feature-dev, code-review, pr-review-toolkit, hookify, plugin-dev, mcp-server-dev, agent-sdk-dev, claude-md-management, security-guidance, 14 LSP plugins, and vetted external context7/serena/playwright/github.
5. **code.claude.com/docs/llms.txt** — 228 pages of harness docs; the single most important reference for anything Claude Code (agent teams, workflows, mods, channels, sandboxing are 2026 additions).
6. **platform.claude.com docs** — prompt engineering (model-specific pages for Fable 5.1 / Opus 5.5 / Sonnet 5.5 / Haiku 5.5), prompt caching, tool use, structured outputs, compaction, Managed Agents, Skills API, `ant` CLI.
7. **claude-api skill** (anthropics/skills) — 616 lines of current API truth (auth resolution, models, features) to load before writing any Claude API code.
8. **Claude Agent SDK** (python 8.4k★ MIT, TS, docs) — the production agent loop with hooks, subagents, skills, MCP; replaces hand-written harnesses.
9. **modelcontextprotocol/servers + spec** — the 7 maintained reference servers (filesystem, git, fetch, memory, sequentialthinking, time, everything); 13 were archived (github, postgres, puppeteer, slack, brave…). MIT→Apache-2.0 transition in progress.
10. **PrefectHQ/fastmcp** (28k★, Apache-2.0; was jlowin) + **mcp-builder skill** — the fastest path to a good server, with Anthropic's tool-design guidance.
11. **upstash/context7** (64k★, MIT) — version-exact library docs; official external plugin; hosted remote server.
12. **microsoft/playwright-mcp** (39k★) and **ChromeDevTools/chrome-devtools-mcp** (54k★) — the two browser servers worth running; vercel-labs/agent-browser (45k★) as the CLI alternative.
13. **oraios/serena** (31k★, GPL-3.0 app / MIT SolidLSP) — semantic code tools over LSP; official external plugin; run as server, don't vendor.
14. **yamadashy/repomix** (29k★) + coderamp-labs/gitingest — context packers with secret scanning and MCP mode.
15. **github/spec-kit** (144k★) and **Fission-AI/OpenSpec** (73k★) — the two spec-driven kits that matter in 2026.
16. **gastownhall/beads** (28k★, MIT) — dependency-graph issue tracker as agent memory; the basis of gastown multi-agent orchestration.
17. **anthropics/sandbox-runtime** (6.8k★, Apache-2.0) + **dagger/container-use** — isolation for unattended agents on this server (Daytona OSS is dead).
18. **promptfoo** (27k★) + **UKGovernmentBEIS/inspect_ai** — eval frameworks; **harbor** (Terminal-Bench 2) and **SWE-bench** for coding-agent benchmarks, with Anthropic's "Demystifying evals" and "infrastructure noise" essays.
19. **langfuse** (37k★, MIT core) — self-hosted tracing/evals/prompt management; OTel-native alternatives phoenix (ELv2), openllmetry.
20. **ollama + llama.cpp**, **docling** (70k★), **transformers/unsloth** — the local-model, document-ingestion and fine-tuning anchors; sized notes for the 4 GB GTX 1650 Ti (2–4B Q4 models only).

Honourable mentions: anthropics/claude-cookbooks (renamed from anthropic-cookbook; patterns/agents, tool_use/context_engineering), Anthropic research series (building effective agents, context engineering, writing tools, harnesses, C compiler with parallel Claudes, auto mode), agentskills.io spec + skills-ref validator, shareAI-lab/learn-claude-code (79k★, harness education), mini-swe-agent.

## 3. Notable agent skills, MCP servers and plugins found (and how they were checked)

- Read in full or skimmed: all 19 anthropics/skills SKILL.md files, all 15 superpowers skills + its SessionStart hook script, mattpocock tdd and grill-me, plugin.json/README of ~25 official plugins, READMEs of ECC, claude-mem, paperclip, hermes-agent, gastown, beads, learn-claude-code, claude-code-templates.
- Pattern scan (ignore-previous / curl|sh / base64 / eval / ~/.ssh / api_key) over all fetched skills: one hit, benign (claude-api documents `ANTHROPIC_API_KEY` resolution). **No hidden instructions found** in anything listed.
- Skills: skill-creator, mcp-builder, claude-api, frontend-design (1M installs), webapp-testing (runs Playwright), document skills (docx/pdf/pptx/xlsx — **proprietary licence**, usable under the Anthropic agreement only), superpowers set, mattpocock set, trailofbits/skills (48 audit skills, CC-BY-SA), vendor packs (cloudflare, supabase, expo, huggingface, aws, azure), K-Dense scientific skills (177).
- Plugins: official feature-dev / code-review / pr-review-toolkit / hookify / plugin-dev / mcp-server-dev / agent-sdk-dev / claude-md-management / claude-code-setup / security-guidance / claude-security / LSP plugins / explanatory-output-style; community: jarrodwatts/claude-hud (statusline), wshobson/agents marketplace, thedotmack/claude-mem (records all tool activity — privacy note).
- MCP: 7 reference servers; context7, GitMCP; playwright-mcp, chrome-devtools-mcp; serena, claude-context, mcp-language-server, sourcebot; github-mcp-server; firecrawl/exa/tavily/brave (keys), crawl4ai (no key); dbhub, postgres-mcp, supabase (→S2); terraform, kubernetes, grafana, aws/microsoft/cloudflare collections (→S4); container-use (sandbox); inspector, MCPJam, mcp-proxy; MCPB, MCP Apps, tunnels, MCP connector; registry live (API checked).
- Safety flags are in each `note:` — "runs shell", "needs API key", "launches a browser", "records session activity", "curl|bash installer".

## 4. Gaps I could not fill

- Did not read all 315 official plugins or ECC's 311 skills; descriptions read, ~25 plugins inspected. The 2,283-plugin community marketplace is listed as an index only.
- skills.sh install counts look gameable (20-star repos with 1.1M "installs", a 16-star `101-skills/superpowers` copycat) — I used them only as a weak signal and excluded those repos.
- Local-model recommendations for 4 GB VRAM come from 2026 blog consensus (Qwen3.x 4B, Gemma 4 2–4B, Llama 3.2 3B at Q4), not from benchmarks run here.
- Claude Code Mods, channels, goal mode and agent teams are new; only docs and the example mods are listed — no mature community mods verified.
- Vector databases (S2), LLM/agent security and prompt-injection defences (S5), CUDA/GPU kernels (S3), chat UI components (S4) are cross-referenced via `see_also`, not catalogued.
- No Windows-specific tooling; no paid-only products (Cursor, Windsurf, LM Studio app) beyond their OSS parts.

## 5. Rejected or down-ranked items (reason)

- **Archived**: anthropics/courses (also CC-BY-NC), daytonaio/daytona (closed-source June 2026, archived Oct 2026; fork nightona-co/nightona AGPL, 23★), Azure/azure-mcp (→ microsoft/mcp catalog), pydantic/mcp-run-python, browserbase/mcp-server-browserbase, RooCodeInc/Roo-Code, appcypher/awesome-mcp-servers, modelcontextprotocol/servers-archived (13 servers), create-python-server/create-typescript-server, protectai/llm-guard, tensorzero/tensorzero, albumentations, huggingface/text-generation-inference, coder/agentapi, wshobson/commands, iannuttall/claude-agents, steipete/agent-rules, rhasspy/piper (→ OHF-Voice/piper1-gpl), pytorch/serve, charmbracelet/mods, run-llama/LlamaIndexTS, mcp-use/mcp-use-ts, mem0ai/mem0-mcp, anthropics/anthropic-tools.
- **Renamed (old names rejected, new ones listed)**: anthropic-cookbook→claude-cookbooks, jlowin/fastmcp→PrefectHQ/fastmcp, cyclotruc/gitingest→coderamp-labs, steveyegge/beads→gastownhall, ryoppippi/ccusage→ccusage/ccusage, everything-claude-code→affaan-m/ECC, claude-flow→ruvnet/ruflo, sst/opencode→anomalyco, All-Hands-AI→OpenHands, supabase-community/supabase-mcp→supabase/mcp, getsentry/sentry-mcp→getsentry/toolkit (FSL licence), stripe/agent-toolkit→stripe/ai, anthropics/dxt→modelcontextprotocol/mcpb, invariantlabs mcp-scan→snyk/agent-scan, NVIDIA/NeMo-Guardrails→NVIDIA-NeMo/Guardrails, explodinggradients/ragas→vibrantlabsai, UKPLab/sentence-transformers→huggingface, microsoft/LightGBM→lightgbm-org, hiyouga/LLaMA-Factory→LlamaFactory, iterative/dvc→treeverse/dvc, block/goose→aaif-goose, laude-institute/terminal-bench→harbor-framework, Kaggle/kaggle-api→kaggle-cli, chonkie-inc→feyninc, Giskard→giskard-oss, alirezadir Machine-Learning-Interviews→AIMLInterviews.
- **Not found**: lunary-ai/lunary, scaleapi/SWE-bench_Pro, huggingface/learn (site only), google-gemini/gemini-cli-extensions (org, not repo).
- **Stale / low quality**: brexhq/prompt-engineering (2023), khangich/machine-learning-interview (2023), visenger/awesome-mlops (2024, no licence), Doriandarko/claude-engineer (2024), Aider-AI/polyglot-benchmark (no licence, 2024 — mentioned in a note only), designed-by-ai/skills and 101-skills/superpowers (suspicious install counts), heygen hyperframes (marketing content).
- **Deliberately not catalogued**: ruvnet/ruflo (claude-flow; 80k★ but enormous surface and performance claims I could not verify — flag for a separate review), NousResearch/hermes-agent (258k★ general-purpose agent, curl|bash installer, outside coding scope), FoundationAgents/MetaGPT and OpenBMB/ChatDev (role-play multi-agent frameworks, marginal for real coding), ECC listed tier 3 reference only (install only individual skills).
- **Licence-limited (listed as reference/mcp, never vendor)**: hesreallyhim/awesome-claude-code (CC-BY-NC-ND), NirDiamant repos (custom non-commercial), firecrawl, Skyvern, siteboon/claudecodeui, basic-memory, ultralytics (AGPL), Serena app, ComfyUI, piper1-gpl, fastbook code (GPL), claude-task-master (Commons Clause), phoenix (ELv2), getsentry/toolkit (FSL), anthropics document skills (proprietary), open-webui (custom), fish-speech (custom), MinerU (Apache + terms).

## 6. Concerns

- **Licences**: the MCP project (spec, TS/Go/Rust SDKs, servers, inspector, registry, mcpb) is mid-transition MIT→Apache-2.0 — record the licence of the pinned commit. GitHub reports `none` for anthropics/skills, claude-code, agent-sdk-typescript and several Anthropic repos; per-folder LICENSE.txt files decide (Apache-2.0 for most skills, proprietary for docx/pdf/pptx/xlsx). langfuse/litellm/mastra/MCPJam/agenta carry `ee/` or enterprise folders under other licences.
- **Safety**: plugins, hooks, mods and MCP servers execute code with the user's permissions; ~20 listed servers need API keys or cloud credentials and several can mutate infrastructure. The community marketplace is unreviewed. Recommend: install only from claude-plugins-official or pinned commits, run `snyk/agent-scan` on anything mirrored, keep Bash sandboxing on, and treat every SKILL.md/README mirrored into the garage as data (the garage should never auto-load third-party skills into sessions without a human enabling them).
- **Hardware fit**: the server's 4 GB GTX 1650 Ti limits local inference to 2–4B Q4 models and whisper base/small; vLLM, SGLang, olmOCR, MinerU-VLM, SAM3 are reference-only here. The owner's Mac is better served by mlx-lm.
- **Size**: mirroring source repos such as pytorch/transformers/vllm is tens of GB; mirror skills, plugins, docs (`.md` pages via llms.txt) and pin library repos by tag instead of cloning them.
- **Churn**: Anthropic docs change weekly (whats-new/2026-w37 is the latest); ~30 repos in this slice were renamed or archived within 18 months. Re-run `ghmeta.py` over the catalog monthly and re-fetch the two llms.txt indexes.
