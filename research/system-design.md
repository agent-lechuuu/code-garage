# Code Garage — system design (Phase 13, research slice S8)

Internal design note, kept as written. "The server", "the owner's Mac", the users and the approval kinds describe the
owner's own setup; nothing here is needed to use the garage (see docs/use-anywhere.md).

2026-10-28. Inputs: BRIEF.md; the server as found today; live checks (ghmeta.py batches, GitHub API tree sizes, Claude Code
2.1.312 `--help`, code.claude.com docs, three research subagents for prior art / safety+licences / plugin mechanics).
Assumes the seven slices land as ~600–1000 topics and 2,000–4,000 resources in the brief's schema (unchanged here).

## 0. The design in one paragraph
One GitHub repo, `code-garage`, is the source of truth: the catalog (the 7 slice YAMLs as written) + a lock file of pinned
commit SHAs + a trust registry + our own glue (CLI, read-only MCP server, one Claude Code plugin, CI). The server keeps a
local mirror of every pinned snapshot under `/data/apps/garage` (btrfs, zstd) so agents read, grep and copy offline;
GitHub holds no third-party code except small trusted, permissively licensed skills. Agents find things through a SQLite
FTS5 index (the lechu-kb design) via the `garage` CLI or the MCP server, and copy things in with `garage add` (pinned
SHA, LICENSE kept, a manifest written). Runnable items (skills, MCP servers, plugins, templates) go quarantine → reviewed →
trusted; unattended agents load trusted only, and nothing becomes trusted automatically. Access: server users get the
plugin from one managed-settings drop-in (nothing per project); the Mac adds the GitHub marketplace plus the tailnet MCP;
"anyone" gets the public repo, a `uvx`/`npx` CLI and a run-it-locally MCP. No inbound traffic to the house, ever.

## 1. Prior art (verified 2026-10-28)
| System | State today | Borrow / avoid |
|---|---|---|
| Context7 (upstash, MIT, 63.8k★, pushed today) | hosted docs index; only the MCP shim is open, crawler/API private; `context7.json` opt-in per repo; `npx ctx7` + remote MCP | borrow the tiny tool surface (resolve → query) and a local run mode; avoid: an index you can't mirror |
| GitMCP (idosal, Apache-2.0, 8.5k★, last push 2026-05) | Cloudflare Worker, fetches llms.txt/README on demand, no index; alive but coasting | zero-index = zero rot but no ranking; its Worker is the template if a public hosted MCP is ever wanted |
| DeepWiki (Cognition) / deepwiki-open (MIT, 18.3k★) | hosted free for public repos (`mcp.deepwiki.com/mcp`); the open one needs an LLM per repo and drifts to a hosted product | LLM-written wikis go stale on every upstream commit and cost money to regenerate: not for us |
| Sourcegraph / Zoekt | Sourcegraph OSS archived 2024-09, Cody Free ended 2025-07, Enterprise from $16k/yr; **Zoekt** standalone (Apache-2.0, 2.0k★, pushed today), index ≈ 3× corpus | ripgrep over the mirror now; Zoekt only if ranked whole-corpus code search is ever needed |
| Official MCP Registry (7.4k★, API v0.1 "preview", `server.json` 2025-12-11 schema) | metaregistry; publish via `mcp-publisher` + GitHub OIDC; sub-registries (Smithery, PulseMCP, GitHub) ETL it and add scans | optional later: expose our MCP-server subset in the same `/v0.1/servers` shape so allow-lists can point at us |
| Smithery / Glama / mcp.so / PulseMCP | Smithery bought by Arcade (2026-08), proxy shutting 2026-10-31; Glama 111k servers with A–D grades, no data licence; mcp.so hand-picked, no API; PulseMCP sunsetting its v0 API | registry *data* is never openly licensed: treat every hosted index as a cache, keep ours in git |
| Docker MCP Registry (MIT, 577★, pushed today) | one `servers/<name>/server.yaml` per server in git, PR-reviewed, Docker builds + signs images (SBOM, provenance) | the only fully forkable registry; the "YAML per item in git, PR to add" shape is ours too |
| GitHub MCP Registry (github.com/mcp, 647 servers) | consumer of the official registry, no API | nothing to borrow |
| Agent Skills spec (agentskills.io, Apache-2.0, 26.7k★) | SKILL.md frontmatter `name/description/license/compatibility/metadata/allowed-tools`, `scripts/ references/ assets/`, < 500 lines, `skills-ref validate` | our skills follow it exactly; Claude Code is a superset |
| skills.sh (`vercel-labs/skills`, MIT, 37k★, npm `skills` 1.7.4) | `npx skills add owner/repo` → canonical copy in `.agents/skills/<name>` + symlinks into `.claude/skills/`; `skills-lock.json` with source, ref, content hash; pins by ref not SHA; telemetry on by default | borrow the canonical-copy-plus-symlink install and the lockfile; fix its flaw by recording the commit SHA |
| anthropics/skills (184k★) · obra/superpowers (MIT, 307k★) · ClawHub (MIT, 9.5k★) | skills repo (per-folder licences; docx/pdf/pptx/xlsx are source-available), the biggest skills framework, OpenClaw's registry with versions + vector search + scanners | superpowers and the Apache-2.0 Anthropic skills are candidates for trusted packs; ClawHub's malware history (section 4) is the cautionary tale |
| shadcn registry (MIT, 126.8k★, CLI 4.23) | `registry.json` → built `public/r/<name>.json` with file **content inlined**; `registryDependencies`, `target` paths; consumers add `"registries": {"@acme": "https://…/r/{name}.json"}`; `npx shadcn add @acme/x`; `shadcn mcp init` gives agents search/add; no consumer-side lock | the proven "copy code in with little modification" shape for our own snippets/templates: a static JSON per item that any host can serve |
| Backstage templates (Apache-2.0, 34.7k★) | `template.yaml` parameters (JSON Schema) + ordered steps; needs Node + Postgres, ≥ 6 GB RAM | far too heavy; borrow only "parameters + steps" for `garage new` |
| copier 9.19 (MIT, Python 3.14 ok) vs cookiecutter 2.7 | copier does `copier update` (re-sync a scaffold to a newer tag, conflicts as markers); cookiecutter has no update, cruft is dormant | copier for templates we expect to re-sync |
| degit 3.10 (revived 2026-10-21) / tiged 2.12 ("time to move on") | tarball-by-ref caches, `#commit` pins, no lockfile | the SHA-keyed tarball cache idea only |
| vendir (Carvel, Apache-2.0, v0.46.3 2026-10-19) | `vendir.yml`: git url + ref + `includePaths` + depth; `vendir sync` writes `vendir.lock.yml` with the SHA; `sync --locked --lazy` | **use it as-is for the mirror**: it is exactly "pin sub-paths of many repos by SHA with a lock" |
| awesome-lint 2.3 (MIT) · lychee 0.24 (Apache-2.0/MIT) | awesome-lint checks list style only, no liveness; lychee checks HTTP status with a cache, GitHub token support; neither sees archived/idle repos | lychee for non-GitHub URLs + a GitHub API sweep (`archived`, `pushedAt`) like awesome-docker's health check |
| Personal libraries: hesreallyhim/awesome-claude-code (56.7k★, CC-BY-NC-ND), iflytek/skillhub (Java+Postgres), skillnote, context-awesome, llms-txt-hub | awesome-claude-code has the best catalog pipeline: a CSV with `Active / Last Checked / Stale`, `config.yaml` categories, a generator, issue-form submissions validated by a workflow, a weekly ticker | borrow the pipeline (we have YAML instead of CSV); skillhub is enterprise weight |
Three ways such catalogs rot: dead/archived repos that HTTP checks still see as 200; "latest" that silently changes
(degit/skills.sh refs); platform drift (Smithery acquired, PulseMCP API sunset, Sourcegraph enterprise-only). Hence:
pinned SHAs, a weekly API sweep, and the data in our own git under an open licence.

## 2. Storage: catalog in git, snapshots on the data disk
Measured today (GitHub API): HEAD working trees of 17 typical repos median 12.8 MB, mean 31 MB (next.js 161 MB); full
histories (GraphQL `diskUsage`) median 92 MB, mean 655 MB, 4 of 20 over 1 GB (TypeScript 2.9 GB, next.js 2.6 GB,
supabase 2.5 GB). The sample skews big; skills/MCP/awesome repos are KBs to a few MB, so real totals are lower.

| Method | Size for 2,500 repos | Update | Verdict |
|---|---|---|---|
| Snapshot of the pinned commit, no `.git` (`git init; git fetch --depth 1 origin <sha>; git archive` → dir) | ~76 GB raw ≈ 30 GB on zstd | only when a pin changes | **use this** |
| Shallow clone kept with `.git` (`--depth 1`) | ~55 GB | `git fetch --depth 1` | ok; `.git` adds ~40 % for no agent value |
| Blobless/partial clone (`--filter=blob:none`) | 2–5× a snapshot, giants dominate; checkout needs network | `git fetch` | no: breaks "offline" |
| Bare mirror of full history (`--mirror`) | ≥ 225 GB by median, 0.8–1.6 TB by mean | `git fetch` | no |
| git submodules in `code-garage` | pointers on GitHub, full clones for every consumer | painful | no (slow, every clone pays) |
| git subtree / vendoring into our history | repo passes GitHub's 1 GB "ideally" and 5 GB "strongly" limits fast; 100 MiB/file hard block | squash merges | no |
| **vendir** (Carvel, Apache-2.0, v0.46.3 2026-10-19): `vendir.yml` with git url + ref (a sha) + `depth: 1` + `includePaths`; `vendir sync --locked --lazy`; `vendir.lock.yml` | same as snapshot (no `.git` kept) | one command, only changed pins | **the mirror tool**: `garage mirror` generates `vendir.yml` from catalog + pins and runs it; `vendir.yml`/`vendir.lock.yml` stay under `/data/apps/garage` (generated), `lock/pins.yaml` in git is the truth; one Go binary (`system.package.install` approval once) |

Rules. (1) Pin = full 40-char commit SHA, fetched by SHA (GitHub serves reachable SHAs; `actions/checkout` and Claude Code's
plugin `sha` pins rely on the same thing) — never a tarball checksum (GitHub itself says pin commit ids, not archive
hashes). `garage pin` checks the sha is upstream's (compare status `behind|identical`, see section 4). On machines without
vendir (the Mac, anyone) `garage add` does the same fetch-by-sha in Python; our own sha256 manifest of the extracted files
goes into `.garage.json`.
(2) Mirror policy by `use`: `vendor|skill|mcp|template|snippet` → whole snapshot (or only `path` when given, via
sparse-checkout); `install|reference` and `kind: docs|guide|list|checklist` → README + `docs/` only (≤ 5 MB) or nothing
but the link. Expect 15–30 GB total; 471 GB free. (3) `/data/apps/garage/mirror` is a nested btrfs subvolume so snapper's
timeline snapshots of `@apps` skip it (nested subvolumes are not in a parent's snapshot); zstd:3 inherited.
(4) Layout `mirror/<owner>__<repo>/<sha12>/` + `.garage.json` (repo, sha, tree, pinned, licence, size, path) and a
`current` symlink; `quarantine/` has the same shape for unreviewed runnable items. (5) Into GitHub: catalog, lock, trust,
schema, tools, plugin, MCP code, docs, generated `INDEX.md` + `dist/catalog.json` (3–5 MB), small trusted skill packs with
their LICENSE. Never: snapshots, SQLite files, archives, media (the brain's `repo-guard` already refuses `.db .sqlite .zip
.gz`, >10 MB; reuse it). The index is rebuilt locally in seconds (`garage index`), not committed.

## 3. Licences (general information from primary sources, not legal advice)
- **No licence** (GitHub ToS §D.5 allows viewing and forking *within GitHub* only; choosealicense: no right to use, modify
  or share): list + link + pinned SHA only. A read-only copy in the server mirror for our own reading is a grey area with
  low practical risk; it is never pushed anywhere. `anthropics/skills` has no root licence: judge per folder (14 skills
  Apache-2.0; `docx/pdf/pptx/xlsx` are "source-available, all rights reserved" → link only; `doc-coauthoring` no licence).
- **Permissive (MIT, BSD, ISC, Apache-2.0, 0BSD/Unlicense, MPL-2.0)**: may be vendored into private and public repos.
  Keep LICENSE, copyright lines and headers; Apache-2.0 §4 also wants the NOTICE file carried and modified files marked;
  MPL keeps changed MPL files under MPL (file-level), fine when vendored unmodified. Our patches go in separate files or
  carry "changed by lechu" notices. Each vendored folder gets `.garage.json` (url, sha, licence, date) as the UPSTREAM record.
- **GPL/LGPL/AGPL**: private use and running as a separate process (fork/exec, CLI, stdio MCP) create no obligation;
  "mere aggregation" in a catalog does not make the catalog GPL. Pasting GPL code into our scripts would. AGPL §13 bites
  only if we *modify* a server and let others use it over the network. Policy: `reference` (and local `install`) allowed,
  `vendor` refused by CI, nothing GPL in the public repo's tree. ToolHive's registry excludes GPL/AGPL entirely — same instinct.
- **CC-BY / CC-BY-SA 4.0** (OWASP Cheat Sheets, OWASP Agentic Skills Top 10, `trailofbits/skills` are BY-SA): vendor
  unmodified with full attribution (creator, notice, licence link, "modifications: none"); SA binds only adapted material,
  so the catalog keeps its own licence. Any checklist of ours that closely paraphrases OWASP must itself be BY-SA (the
  one in section 4 is written in our own words; the builder should keep it that way).
- **Never vendor**: Semgrep rules/`semgrep/skills` (internal-use licence, no redistribution), gated model weights (Llama
  Prompt Guard), "all rights reserved" skills, `NOASSERTION` until read by hand.
- **Detection at scale**: GitHub's `licenseInfo` (Licensee under the hood, zero CPU, 60 calls for 3,000 repos) is the first
  pass; `licensee` (MIT, Ruby, v10.1 2026-08) on every vendored folder and every `NOASSERTION`; ScanCode (v32.5) is
  file-level and slow (hours for a big repo) — only for what goes public; `reuse lint` (REUSE 6.2) checks *our* repo.
- **Our licences**: code (CLI, MCP, plugin) MIT; our prose CC-BY-4.0; third-party content keeps its own. Public-repo
  default: link-only for everything; vendor only permissive items that passed the review in section 4; takedown within 7 days.

## 4. Safety: quarantine → reviewed → trusted
Why it matters (2026): Koi Security found 341 malicious skills among ClawHub's 2,857 (Feb 2026, one campaign shipping a
macOS stealer); Snyk's ToxicSkills found 76 malicious of 3,984 and 36.8 % with some flaw (fake "prerequisites" that curl|sh,
base64 payloads, "ignore previous instructions", Unicode smuggling, edits to agent memory files). After VirusTotal scanning
was added, Unit 42 (June 2026) still got skills through with 22 MB padding, paste-site payloads swapped after publishing,
instructions fetched at runtime and cron persistence. Cisco's own numbers: rules alone catch 7.7 % at HIGH, rules + LLM
judge 66.7 % with 15 % false positives. So: scanners filter, pins and a human gate, sandboxes contain.

Tiers (field `trust` in `trust/registry.yaml`, keyed by resource url; applies to `use: skill|mcp|template|vendor` with code):
| Tier | How an item gets there | What may happen with it |
|---|---|---|
| `quarantine` (default) | merged into the catalog, mirrored under `quarantine/` | agents may *read* it as data (`garage show`, `garage grep`); `garage add/skill/new` refuse it; never in the plugin |
| `reviewed` | automated gate passed **and** a reviewer walked the checklist and wrote the record (sha, scanner versions, findings, waivers) | loadable in interactive sessions; the agent says "reviewed, not yet trusted" when it uses one |
| `trusted` | reviewed + owner's tap (weekly Telegram card listing the week's reviewed items) + first run observed in a throwaway sandbox | loadable unattended (`lechu-job`, the assistant); only tier shipped in `plugins/packs/` and as pinned marketplace entries |
Nothing moves up automatically; a pin bump moves `trusted` → `reviewed` (CI: a trust record is valid only for the pinned sha).

Automated gate (`garage scan ID`, all local, no keys): (1) NVIDIA **SkillSpector** `--no-llm` (Apache-2.0, 22.9k★, 71
patterns: injection, exfiltration, hidden unicode, typosquats, OSV-known-vulnerable deps; exit 1 = do not install);
(2) **Aguara** `audit --ci` (Apache-2.0, Go binary, 258 detections incl. hooks and `.claude/settings.json` inside the
item; single maintainer, so treat as second opinion) or Cisco **skill-scanner** static mode (YARA-X, `.pyc`, shell taint;
Apache-2.0, 2.7k★); (3) **gitleaks** (already on the server); (4) our own 60-line checks: invisible/bidi/tag characters
(U+200B–200D, U+2060, U+FEFF, U+202A–202E, U+2066–2069, U+E0000–E007F), base64/hex blobs > 200 chars, override phrases
("ignore previous instructions", "do not tell the user", "you are now"), runtime fetches of instructions (URLs in SKILL.md
that are not docs links), curl|sh, install hooks (`postinstall`, `setup.py` code, `.pth`), cron/systemd/rc writes, text
files > 1 MB or item > 10 MB, binaries/minified/archives, hooks or `.mcp.json` inside the item, dependency count and
lockfile presence; for MCP servers: Cisco **mcp-scanner** YARA mode on `tools.json`, tool descriptions read in full for
hidden instructions. Not used: Snyk agent-scan (sends content to Snyk's API and starts the servers), mcp-shield/guardian
(stale since 2025), prompt-injection classifiers (ProtectAI's is archived and false-positives on instruction files;
Prompt Guard 2 is gated) — a score at most, never a gate. Semgrep has no MCP/skills ruleset and its rules can't be vendored.

Reviewer checklist (`docs/safety.md`, ~25 points, in our own words; sources OWASP Agentic Skills Top 10, Snyk, Unit 42,
Claude Code docs): full 40-hex sha reachable from upstream's default branch or a tag (**fork gotcha**: GitHub serves a sha
that exists only in a fork through the upstream URL — `gh api repos/o/r/compare/<default>...<sha>` must say `behind` or
`identical`); publisher real (account age, other repos, no typosquat); maintained in the last 12 months; licence per
folder; scanner findings triaged not ignored; no secrets; declared shell/network/filesystem scope matches what the code
does (`allowed-tools` reviewed, no blanket `Bash(*)`; no reads of `~/.ssh`, `.env`, wallets, browser profiles); no
persistence; no remote instruction loading; dependencies pinned, `osv-scanner` clean; first run in a sandbox with egress
logged under `claude -p` with `--settings '{"disableAllHooks":true}'`; the record names who, when, sha, scanner versions.
Claude Code gotcha the builders must respect: under `-p`/SDK (how `lechu-job` runs) project `.mcp.json` servers and hooks
run **without** a prompt — so garage templates never ship `.mcp.json`/hooks, and the hook (`lechu-claude-hook`) gets a rule
denying execution from `/data/apps/garage/quarantine/**` for user `claude` (a `config.change`, so the owner approves it).

How agents learn the rule: the plugin SKILL has a 4-line "Trust" section; every `garage` result line carries `trust`;
`garage show` prints the tier first; the `librarian` agent filters `--trust reviewed` interactively and `--trust trusted`
when `GARAGE_UNATTENDED=1` (set by `lechu-job`'s environment) — one env var is the whole contract.

## 5. Search and retrieval for agents
- Index: SQLite FTS5, ported from `/usr/local/bin/lechu-kb` (one file, stdlib + PyYAML, 8 ms today over 4,200 files).
  Rows: topics (title, why, practices, tags), resources (name, note, kind, use, licence, trust, stars), doc chunks from
  the mirror (first 4 KB of README / full SKILL.md frontmatter+body), bm25 weights title 8 > name 6 > tags 4 > note 3 >
  body 1, `porter unicode61`, AND then OR fallback, results folded per topic. ~1k topics + 3k resources + 5k chunks →
  < 60 MB, single-digit ms. `catalog/synonyms.yaml` expands query words (auth → authentication oauth login session).
- Filters: `--kind`, `--use`, `--slice`, `--trust`, `--license permissive`. Agents mostly ask "I need X" → top 5 topics
  with their best resource each, then `garage show ID` for the recipe (install line, vendor path, local mirror path,
  licence, practices, see_also). Every answer ≤ ~3 KB: Claude Code warns above 10k tokens per MCP result.
- Code search inside the mirror: `garage grep ID PATTERN` = ripgrep scoped to one snapshot (sub-second on a 50 MB tree);
  whole-mirror grep (30 GB) takes minutes and is not offered through MCP. Zoekt (Apache-2.0, active) is the right tool for
  whole-corpus trigram search but its index is about the size of the source plus a Go service and RAM: defer.
- Embeddings: not in v1. If misses show up in the logs, add a hybrid: model2vec static embeddings (`potion-base-8M`, MIT,
  CPU, microseconds per query) + sqlite-vec (Apache-2.0) — 4k vectors × 256 dims is trivial, no GPU needed.
- Retrieval is the same code in three places: the CLI, the stdio MCP (plugin) and the HTTP MCP (stack); one module,
  `tools/garage/search.py`, with a JSON output the plugin and MCP format. MCP runtime: the official Python SDK `mcp`
  (MIT, 24.7k★; stdio and streamable HTTP in one package). On the server `infra/install.sh` makes `/opt/garage/venv`
  (PyYAML + mcp, the console's `/opt/lechu/venv` pattern); the plugin's `bin/garage-mcp` wrapper uses that venv when
  present, else `uvx --from git+https://github.com/agent-lechuuu/code-garage garage-mcp` (the Mac, anyone).

## 6. Access paths
(a) Builders on this server (users `lechuuu`, `claude`, `user`; Claude Code sessions and `lechu-job` runs).
- One root-owned drop-in `/etc/claude-code/managed-settings.d/garage.json`:
  `extraKnownMarketplaces: {"code-garage": {"source": {"source": "directory", "path": "/data/apps/garage/repo"}, "autoUpdate": false}}`,
  `enabledPlugins: {"garage@code-garage": true}`. A `directory` marketplace is read in place (no copy), so every user has
  the plugin at the next session; `git pull` by the sync timer updates it, `/reload-plugins` live. Nothing per project,
  so hackathon builds "just have" it. The `claude` user's `Edit(~/.claude/plugins/**)` deny stays: registration is done
  by Claude Code itself, not by the Edit tool (verify once under its sandbox; fallback `CLAUDE_CODE_PLUGIN_SEED_DIR`).
- The plugin puts `bin/garage` on Bash's PATH and declares a stdio MCP: `python3 -I ${CLAUDE_PLUGIN_ROOT}/mcp/server.py`
  with `GARAGE_HOME=/data/apps/garage` — read-only, local files, no network, runs as the session user.
- Later hardening: `strictKnownMarketplaces` = official + code-garage + `skills-dir`, `disableSideloadFlags: true`.
- `garage new NAME [--template ID]` scaffolds a project from a trusted template and writes `CLAUDE.md`: "search the
  garage before building anything; cite the garage id in the commit".
(b) The owner's Mac (Claude Code, tailnet).
- `claude plugin marketplace add agent-lechuuu/code-garage` → the same plugin; its stdio MCP and CLI use the bundled
  `dist/catalog.json` + `lock/pins.yaml`, so search works offline and `garage add` fetches the pinned SHA from GitHub.
  Private repo: add the owner's GitHub login as collaborator and run `gh auth setup-git` on the Mac (Claude Code clones
  with the user's git credentials; no token field). Pin the marketplace to a tag, `autoUpdate: false` (the default).
- Richer, optional: `claude mcp add --transport http garage https://garage.<your-tailnet>.ts.net/mcp --scope user
  -H "Authorization: Bearer …"` → the server's index including mirrored READMEs and `garage grep`. A `garage` stack like
  search: `ts.yml` sidecar (tag:svc), app container read-only with `/data/apps/garage:ro`, mem 128m, token from
  `lechu-secret`. Big snapshots: `garage add ID --from lechu` = rsync over the owner's existing SSH access.
(c) Anyone on the internet (after the repo is public, decision 2).
- `claude plugin marketplace add agent-lechuuu/code-garage` works for anyone; so does `uvx --from
  git+https://github.com/agent-lechuuu/code-garage garage search …` and `npx github:agent-lechuuu/code-garage` — no npm or
  PyPI account needed (publish there later if the owner wants the short names).
- GitHub Pages (free on public repos, paid plan on private) serves `INDEX.md` + `dist/catalog.json` as a browsable site and
  a static shadcn-style registry for our own snippets.
- Hosted MCP: not from the server. The server accepts no inbound traffic, and `tailscale funnel` is on the approval list;
  claude.ai cannot reach tailnet names. The "MCP for anyone" is the plugin's stdio server running on their machine over
  the public catalog (Context7's local mode works the same way). If ever wanted: a Cloudflare Worker serving the same
  read-only tools from the static catalog (GitMCP's model) — a separate decision and account.

## 7. Freshness and growth (almost no LLM)
- `garage-verify.timer`, weekly (Sun 04:30, no Claude): ghmeta over every GitHub URL (≤ 70 GraphQL calls of 50 repos;
  the budget is 5,000/h), detecting archived, moved (nameWithOwner changed), gone, licence changed, stars/pushed; lychee
  (Apache-2.0, active) for non-GitHub URLs with a cache. Output: a branch + PR "verify 2026-W44" that updates metadata and
  a 20-line `reports/verify-2026-W44.md` (archived → tier 3 + note, moved → url rewrite, gone → remove/replace). Pure
  metadata changes may auto-merge; anything that changes a recommendation waits for the owner's tap in GitHub.
- Pins never move on their own. `garage pins --outdated` lists upstream movement; a monthly "pin bumps" PR shows the diff
  stats; merging a bump drops a runnable item from trusted to reviewed until re-reviewed (CI enforces).
- Growth: in any session, `garage propose URL --topic ID --why "…"` verifies with ghmeta, scans runnable items, writes
  `proposals/<date>-<slug>.yaml` and opens a PR. As user `claude` the push to a non-brain repo triggers the Telegram
  approval card (`git.push_elsewhere`), as `lechuuu` it is direct. CI validates; the owner merges from GitHub mobile.
  Merged proposals enter as `trust: quarantine` and are mirrored on the next sync. Once public, outsiders propose through a
  GitHub issue form that a workflow validates (awesome-claude-code's pattern) — no write access needed.
- Claude usage: the weekly loop costs zero. Optional monthly p3 Haiku job `garage-digest` (~0.3 governor points): one app
  message summarising open proposals and the verify report. `claude plugin eval` only by hand (real model calls).

## 8. The repository `agent-lechuuu/code-garage`
```
README.md                      what it is, the three ways to use it (short, hand-written)
INDEX.md                       generated: slice → area → topic → resources with trust badge, licence, stars
catalog/<slice>.yaml           the 7 slices, brief schema, human-edited; catalog/garage.yaml = our own templates/snippets
catalog/synonyms.yaml          search synonyms
lock/pins.yaml                 url → {sha, tree, pinned, size_kb, license_at_pin, path}   (machine-written: `garage pin`)
trust/registry.yaml            url → {trust, scans: [{tool, version, date, result}], reviewed_by, date, notes}
proposals/                     agent proposals awaiting a decision (each is a PR)
reports/                       weekly verify reports (20 lines each)
schema/                        catalog.schema.json, pins.schema.json, trust.schema.json
tools/garage/                  CLI: search show grep add skill new propose pin mirror verify index scan promote validate
plugins/garage/                .claude-plugin/plugin.json, skills/{find,use,propose}/SKILL.md, agents/librarian.md, bin/garage, mcp/server.py, .mcp.json
plugins/packs/<name>/          trusted, permissive third-party skills copied in with their LICENSE (KBs each)
.claude-plugin/marketplace.json  plugins: garage (./plugins/garage), the packs, and pinned upstream plugins (git-subdir/url + sha)
stacks/garage/                 compose.yml, ts.yml, Dockerfile for the tailnet MCP (stackctl policy: mem limit, read-only)
infra/                         managed-settings.d/garage.json, systemd garage-sync.timer + garage-verify.timer, install.sh (root)
dist/catalog.json              generated merged catalog + pins + trust (3–5 MB) for the plugin, the Mac, anyone
docs/                          use-on-server.md use-on-mac.md use-anywhere.md licences.md safety.md (checklist) contributing.md
.github/workflows/validate.yml schema, unique ids, licence/trust policy, INDEX+dist freshness, lychee — on every PR
.pre-commit-config.yaml        gitleaks, repo-guard, yamllint (copied from the brain) + `garage validate`
LICENSE                        our glue: MIT. Third-party content keeps its own licences (docs/licences.md)
```
Marketplace precedent: Anthropic's own `claude-plugins-official` (315 plugins) pins external plugins exactly this way
(`source: {source: url|git-subdir, url, path, sha}`), so `claude plugin validate .` is the only tooling we need.
GitHub account: the server is `agent-lechuuu` and its fine-grained token reaches only `lechu-brain`. The owner creates
`code-garage` (private) under `agent-lechuuu` and adds it to that token with Contents, Pull requests and Workflows
read/write (Pages later). Putting it under the owner's own account does not work for the server: a fine-grained PAT can
only reach repositories its owner owns, so the server could not push. Actions minutes: 2,000/month free on private
repos (~2 min per PR), unlimited on public. `gh repo create` by the assistant is on the approval list anyway.

## 9. Build tracks (parallel Opus builders) and the test
| Track | Owns (files) | Delivers | Contracts |
|---|---|---|---|
| T1 Catalog + CLI + CI | `catalog/`, `schema/`, `tools/garage/` (except mirror/verify/scan), `INDEX.md`, `dist/`, `.github/`, `docs/contributing.md`, `catalog/synonyms.yaml` | merge of the 7 slices (ids unique, see_also resolved), `garage validate|index|search|show|add|skill|new|propose`, generated INDEX/dist, CI | publishes `schema/*.json` and the CLI `--json` shapes on day 0; search module API |
| T2 Mirror + freshness | `lock/`, `tools/garage/{mirror,pin,verify}.py`, `infra/systemd/`, `/data/apps/garage/*` layout, `reports/` | nested subvolume, `vendir.yml` generated from pins + `vendir sync --locked --lazy`, Python fetch-by-sha fallback, `.garage.json`, `current` links, weekly verify PR, pin-bump PR | `pins.yaml` format, snapshot layout, `GARAGE_HOME` env |
| T3 Plugin + MCP + access | `plugins/garage/`, `.claude-plugin/marketplace.json`, `plugins/packs/`, `stacks/garage/`, `infra/managed-settings.d/`, `infra/install.sh`, `docs/use-*.md` | plugin (skills, librarian agent, bin, stdio MCP), HTTP MCP stack, admin install, Mac + anyone docs | consumes T1's search module and `dist/catalog.json`; mounts T2's paths read-only |
| T4 Safety | `trust/`, `tools/garage/scan.py`, `tools/garage/promote.py`, `schema/trust.schema.json`, `docs/safety.md`, CI policy rules, proposed `approvals.yaml`/hook rule text | scanner wrapper (SkillSpector, Aguara or Cisco, gitleaks, own checks), review checklist, promotion rules enforced in CLI + CI, the weekly owner card, the SKILL "Trust" text | trust values, `GARAGE_UNATTENDED`, and the rules are frozen on day 0 so T1/T3 can enforce them |
Order: T1 publishes schemas and the search module first (half a day), then all four run; integration on day 2 with 20
mirrored items, 10 scanned skills, one trusted pack, one pinned upstream plugin. Builders don't touch `/srv/brain`.
Documented but not yet tested here — verify on day 1: a managed `directory` marketplace registering for user `claude`
inside its sandbox (fallback: `CLAUDE_CODE_PLUGIN_SEED_DIR`); vendir fetching a bare commit sha with `depth: 1`;
SkillSpector and Aguara running cleanly on Python 3.14 / this kernel; `lechu-ask` callable from the garage sync user.
Sonnet tester, end to end: (1) fresh empty dir as `lechuuu`, `claude` → "I need a headless dialog in React" → the garage
skill fires, `garage search` returns Radix with install line and licence in < 1 s and < 3 KB; (2) `garage add <id> --into
vendor/` copies the pinned snapshot + LICENSE and writes `vendor/<name>/.garage.json`; (3) `garage skill add <trusted id>`
lands in `.claude/skills/` and loads; the same for a quarantine id is refused with the reason; (4) as user `claude`
inside its sandbox: plugin loads, MCP answers, no write outside allowed paths, `lechu-claude-hook` log shows the calls;
(5) Mac: marketplace add + HTTP MCP work, `claude plugin details garage` shows < 2k tokens of context cost;
(6) CI fails a PR with a duplicate id, a `vendor` resource under GPL, or `trusted` without a review record; (7) a dry-run
`garage verify` flags a repo archived on purpose in a test fixture; (8) `garage propose` as `claude` raises the Telegram
approval card and nothing is pushed before the tap; (9) rebuilding the index from scratch takes < 1 min.

## 10. Decisions for the owner (plain words)
1. **Where the repo lives.** Recommend: you create `code-garage` under the `agent-lechuuu` GitHub account and add it to
   the server's token (Contents, Pull requests, Workflows). Trade-off: everything stays in the one bot account you
   already have (what you prefer); if it were under your own account the server could not push to it.
2. **Private now, public later.** Recommend: private until the licence pass is done (section 3), then flip to public so
   anyone can `marketplace add` it and GitHub Pages/Actions become free. Trade-off: public means every copied file must
   be allowed to be redistributed and the list carries your name; private means only you and the server use it.
3. **How much to mirror on the server.** Recommend: snapshots of everything vendorable/runnable plus READMEs of the rest
   (15–30 GB of the 471 GB free), not full histories (hundreds of GB to 1.6 TB). Trade-off: a few GB more disk versus
   agents that keep working when GitHub or the internet is down.
4. **Who promotes to trusted.** Recommend: scanners + an Opus review make an item "reviewed"; once a week you get one
   Telegram card listing the reviewed items and one tap makes them "trusted". Trade-off: one tap a week from you versus
   letting the machine decide what unattended agents may run.
5. **Tailnet MCP for the Mac now or later.** Recommend: now — it is the same sidecar pattern as search, about an hour of
   build, and gives the Mac the server's full index and mirror without a 30 GB clone. Trade-off: one more container to
   keep healthy versus a Mac that only sees the catalog file.
