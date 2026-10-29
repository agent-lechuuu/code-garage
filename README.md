# Code Garage

A curated, pinned library of existing code for AI coding agents: repos, agent skills, MCP servers, starter templates,
docs and practices, for most of what people build. Every entry has a licence, a pinned commit and a trust level.

> You don't have to implement and build everything from scratch. Save everything locally and just use it with
> little to no modifications. (The idea the garage is built on.)

The agent searches the garage first, copies what fits, and writes code only for the gap. It is made for agents; a person
can read it too.

## What is in it

977 topics and 4,129 resources (440 you can copy or run; the rest are links, docs and install lines), in 7 slices.
Full lists with licence, stars and trust: [INDEX.md](INDEX.md) and one page per slice in `dist/index/`.

| Slice | Topics | Resources | Covers |
|---|---|---|---|
| [ai](dist/index/ai.md) | 105 | 439 | skills, Claude Code, MCP, agents, prompting, LLM apps |
| [backend](dist/index/backend.md) | 150 | 736 | runtimes, APIs, auth, jobs, databases, safe DB practice |
| [engineering](dist/index/engineering.md) | 158 | 774 | algorithms, architecture, testing, git, CI, DevOps, SRE |
| [frontend](dist/index/frontend.md) | 150 | 717 | frameworks, components, design, animation, 3D, a11y, performance, codepens |
| [security](dist/index/security.md) | 150 | 675 | web vulnerabilities, crypto, secrets, supply chain, scanning, hardening |
| [systems](dist/index/systems.md) | 150 | 714 | C, C++, Rust, Go, memory, concurrency, shell, Linux, WASM |
| [web3](dist/index/web3.md) | 114 | 500 | EVM, Solidity, DeFi, Solana, L2, zero knowledge |

The data: `catalog/*.yaml` (one file per slice), `lock/pins.yaml` (the exact commit of each item), `dist/catalog.json`.
Research reports: `research/`.

## Three ways to use it

- **On the owner's server** (the reference install): the plugin is enabled for every session. [docs/use-on-server.md](docs/use-on-server.md)
- **On the owner's Mac:** the plugin, plus the server's copies over Tailscale. [docs/use-on-mac.md](docs/use-on-mac.md)
- **Anyone:** the plugin or `uvx`, no server needed. [docs/use-anywhere.md](docs/use-anywhere.md)

## Trust (details: [docs/safety.md](docs/safety.md))

- `quarantine`: the default. Read only: `garage show`, `garage grep`. `garage add` refuses it.
- `reviewed`: scanners passed and a reviewer walked the checklist. Fine in interactive sessions; the agent says so.
- `trusted`: reviewed, and the owner approved it on the weekly card. The only tier unattended jobs may use.
- A trust record belongs to one commit. When the pin moves, the item goes back to quarantine.

Today 9 items are `trusted` (the owner's approval on 2026-10-29: cJSON, frontend-design, mcp-builder, skill-creator, webapp-testing, MCP fetch and git, superpowers brainstorming and systematic-debugging) and 6 more are `reviewed`.

## Licences

Each item keeps its own licence. `garage add` copies its LICENSE and NOTICE and writes a `.garage.json` record.
Items with no licence, or a restrictive one (GPL, source-available, non-commercial), are links only. Our own code
(the CLI, the MCP server, the plugin, the install scripts) and docs are MIT; the catalog data, trust records and
reports (`catalog/`, `lock/`, `trust/`, `dist/`, `INDEX.md`, `reports/`, `research/`) are CC-BY-4.0. Both are in
[LICENSE](LICENSE). This repository stores no third-party code.

## How it stays fresh

- Daily on the server: the mirror re-fetches the pinned commits (no Claude involved).
- Weekly: a sweep of every GitHub repo and link finds archived, moved, gone and re-licensed items and opens a pull
  request with a short report. Pins never move by themselves.
- Weekly: an AI reviewer reads up to 3 runnable items and records a verdict; the owner's tap makes the good ones trusted.

## Propose something

`garage propose URL --topic TOPIC_ID --why "one line"` writes a proposal file (`proposals/DATE-name.yaml`) and never
pushes. Open it as a pull request; CI validates it. Accepted proposals start in quarantine.
The `garage:propose` skill in the plugin does the same from a Claude Code session.

## Check the repo

`garage validate` (catalog), `garage build --check` (INDEX.md and dist are up to date), `garage doctor`.
CI runs the first two (`.github/workflows/validate.yml`).
