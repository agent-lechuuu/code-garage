# S6 `engineering` — research report (2026-10-28)

Catalog: `engineering.yaml` — **158 topics, 774 resources** (616 GitHub repos verified live with ghmeta.py in 23 batches;
~160 non-GitHub URLs checked with curl; licence files read for every repo GitHub reports as NOASSERTION).
Resource mix: 290 tools, 205 repos, 161 docs/guides, 23 lists, 22 MCP servers, 21 skills/plugins, 17 templates.
Licences: MIT 258, Apache-2.0 220, BSD 33, MPL 17, CC-BY 52, CC0 12, GPL/AGPL 23, "none" 100 (mostly docs sites and
unlicensed awesome-lists; every `use: vendor` item is permissively licensed). Tiers: 623 tier-1, 143 tier-2, 8 tier-3.
Cross-links: 81 internal `see_also`, 83 to other slices (mapped to their real ids after reading their YAML files).

## Map of the slice (area → topics)

| area | topics | what an agent finds there |
|---|---|---|
| algorithms + cs-fundamentals | 22 | per-language reference implementations, CP libraries (cp-algorithms, KACTL, AC Library), graphs/shortest paths, DP, strings/tries/suffix structures, similarity+diff, geometry+spatial indexes, number theory, DSU, segment/Fenwick/interval trees, heaps, non-crypto hashing, probabilistic sketches, consistent hashing, rate limiting, LRU/LFU caches, complexity/latency napkin math, interview prep, free textbooks, CS curricula, parsing |
| system-design | 15 | primers, distsys fundamentals, consistency models, Raft, CRDTs/local-first, retries+idempotency, circuit breakers+backpressure, sagas/outbox/durable workflows, event sourcing, caching strategies, sharding, distributed locks, distributed IDs, API design + contract specs, feature flags |
| architecture | 15 | pattern catalogs + well-architected, clean/hexagonal/modular monolith, microservices reference apps, DDD, design patterns, refactoring, clean code/naming, code review, C4/Structurizr/arc42, ADRs, 12-factor config, error handling, architecture tests, DORA/handbooks, CLI design |
| testing | 20 | strategy, unit frameworks, mocking, property-based+fuzzing, mutation, snapshot, contract, e2e browser, browser automation for agents, visual regression, load, microbenchmarks, fake data, Testcontainers, mock servers+replay, TDD/BDD, coverage, formal methods+simulation, CLI testing, infra/policy/local-cloud testing |
| documentation | 9 | Diátaxis/tech writing, READMEs, style guides + prose lint, doc SSGs, OpenAPI render+lint, code reference generators, changelogs+semver, diagrams as code, llms.txt |
| git | 8 | conventional commits, branching + stacked PRs, hooks, learning/recovery, CLI tools, monorepo build systems, community health files, licensing compliance |
| ci-cd | 13 | GHA fundamentals+act, reusable/composite/matrix/cross-compile, security hardening+linting, self-hosted runners + alt CI, release automation, caching, image builds, GitOps+progressive delivery, dependency bots+PR automation, AI review in CI, OIDC+attestation, quality gates+test reports, IaC in CI |
| devops | 29 | Dockerfile, Compose, runtimes+registries, K8s learning, production checklist, light distros+dev loop, Helm, Kustomize/CUE, operators, Gateway API+mesh, certs+DNS, storage+backup, autoscaling+policy, secrets, Terraform/OpenTofu (3 topics), Pulumi/CDK, Ansible, Nix (2), self-hosted PaaS, home-server platforms, reverse proxies, Tailscale/tunnels, VMs/images, platform eng+FinOps, cron, backups+object storage |
| observability + sre | 12 | OTel, Prometheus, alert rules+long-term storage, Grafana as code, logs, tracing backends, error tracking, uptime+home-server monitoring, notifications, SRE books/SLOs, incidents/postmortems/runbooks, chaos |
| devex | 7 | task runners+watchers, toolchain/env managers, devcontainers+remote dev, polyglot formatters, scaffolding, codemods, API clients |
| agents | 8 | process skills, Claude Code plugins/subagents, AGENTS.md/rules, MCP for git forges, MCP for Docker/K8s, MCP for IaC/cloud/PaaS, MCP for observability, MCP runtime safety |

## The 20 most valuable resources and why

1. **TheAlgorithms/Python (+Java/Rust/C++)** — MIT, tested, the biggest copy-ready algorithm corpus; the owner asked for this first.
2. **cp-algorithms + AtCoder Library (CC0) + KACTL** — explanations plus dense verified code for every advanced structure; ACL is the safest to vendor.
3. **donnemartin/system-design-primer** — still the reference for design discussions and estimates.
4. **etcd-io/raft / hashicorp/raft** — production consensus libraries; pair with raft.github.io and the Secret Lives of Data animation.
5. **Yjs / Automerge / Loro** — the three CRDT engines; local-first essay explains when to use them.
6. **tenacity / resilience4j (+ AWS backoff & Builders' Library articles)** — retries with jitter and budgets done right; the practices block captures the rules.
7. **Temporal** — MIT durable workflows; replaces hand-written saga/outbox code for most cases.
8. **Playwright + Playwright MCP + Playwright Test Agents** — e2e framework and the official agent-facing planner/generator/healer.
9. **Hypothesis / fast-check / proptest** — property-based testing in the three main stacks.
10. **Testcontainers (java/go/python/node)** — real dependencies in integration tests with one API shape.
11. **k6 + Locust + Vegeta** — load testing from scripts, with p95/p99 thresholds.
12. **obra/superpowers** — the strongest process-skill library (TDD, systematic debugging, verification, plans, worktrees); MIT, reviewed for injection.
13. **anthropics/claude-plugins-official** — code-review, pr-review-toolkit, commit-commands, feature-dev, code-simplifier, code-modernization; Apache-2.0. Note: `anthropics/claude-code/plugins` is now only a pointer here.
14. **github/awesome-copilot** — 447 skills incl. github-actions-hardening, create-ADR, incident-postmortem, multi-stage-dockerfile; MIT.
15. **zizmor + actionlint + pinact** — the current GHA security/lint trio; practices cover SHA pinning and injection.
16. **release-please / goreleaser / cargo-dist** — release automation per stack from conventional commits.
17. **OpenTofu (MPL) + terraform-best-practices + Terraform MCP Server** — IaC default, style, and registry docs for agents.
18. **k3s + kind + Tilt** — Kubernetes on a home server and fast dev loops.
19. **Caddy / Traefik + Tailscale / Headscale + Pangolin** — the home-server edge: HTTPS, routing, private access.
20. **OpenTelemetry collector + Prometheus + Grafana + Loki/Alloy + Uptime Kuma + ntfy** — the complete self-hosted observability path with Grafana-as-code via Foundation SDK.

Honourable mentions: Coolify/Dokploy/Kamal (PaaS), restic/borg/kopia (backups), mise + just (devex), pre-commit → prek (hooks),
Renovate (deps), Diátaxis + Material for MkDocs (docs), ArchUnit/import-linter/dependency-cruiser (architecture tests).

## Notable agent resources found

- **Skills**: obra/superpowers (15 skills), anthropics/skills (webapp-testing, skill-creator, mcp-builder), awesome-copilot
  (447 skills), VoltAgent/awesome-agent-skills (1000+ index), tommy0103/better-readme-skill (small). Read fully:
  webapp-testing, superpowers TDD + systematic-debugging, awesome-copilot github-actions-hardening + create-ADR — no
  agent-directed injection; grep hits for "secret/token" were topical.
- **Plugins/subagents**: claude-plugins-official (36 plugins + 14 external), wshobson/agents (~100 plugins; cicd-automation,
  kubernetes-operations, tdd-workflows, debugging-toolkit, incident-response, observability-monitoring, c4-architecture),
  VoltAgent/awesome-claude-code-subagents (categories 03-infrastructure, 04-quality-security, 06-developer-experience),
  davila7/claude-code-templates, intellectronica/ruler (one rules source → CLAUDE.md/AGENTS.md/.cursorrules).
- **MCP servers (22 listed)**: github/github-mcp-server, modelcontextprotocol/servers (git/fs/fetch), zereight/gitlab-mcp,
  docker/mcp-gateway, containers/kubernetes-mcp-server, patrickdappollonio/mcp-kubernetes-ro (read-only — recommended default),
  Flux159/mcp-server-kubernetes, argoproj-labs/mcp-for-argocd, hashicorp/terraform-mcp-server, awslabs/mcp (iac/eks/ecs/
  cloudwatch/cost), microsoft/mcp (Azure), cloudflare/mcp-server-cloudflare, StuMason/coolify-mcp, grafana/mcp-grafana,
  pab1it0/prometheus-mcp-server, getsentry/toolkit (ex sentry-mcp), traceloop/opentelemetry-mcp-server, grafana/mcp-k6,
  upstash/context7, microsoft/playwright-mcp, ChromeDevTools/chrome-devtools-mcp. Runtime: stacklok/toolhive, Docker MCP Gateway.
- **Renames to know**: podman/skopeo/buildah → podman-container-tools org; velero → velero-io; sealed-secrets → bitnami;
  sst → anomalyco; terrastruct/d2 → d2lang; errata-ai/vale → vale-cli; akuity/argocd-mcp → argoproj-labs/mcp-for-argocd;
  MarcoIeni/release-plz → release-plz; informalsystems/quint → quint-co; nedbat/coveragepy → coveragepy; probot/settings →
  repository-settings/app; github/safe-settings → github-community-projects; getgrit/gritql → biomejs; qodo pr-agent → The-PR-Agent (MIT).

## Gaps I could not fill well

- Bit-manipulation reference (Stanford "Bit Twiddling Hacks" host unreachable during verification) — not listed.
- Several canonical blog posts are bot-blocked (Medium: Pinterest sharding, Netflix tech blog; ACM Queue "There is no now";
  infiniteundo time falsehoods) — omitted rather than listed unverified; kdeldycke/awesome-falsehood covers the last one.
- No strong open-source on-call scheduler: Grafana OnCall OSS archived, linkedin/oncall slow; Keep (MIT+ee) is the best left.
- Helm, Ansible, Pulumi, Proxmox, Tailscale MCP servers exist only as small community projects (≤150 stars) — noted in notes, not promoted.
- Structured-logging library guidance per language belongs to S2/S3; only pipelines/storage are here.
- Multi-tenancy/SaaS patterns reduced to the AWS SaaS Lens mention (no good open implementation found).
- 158 topics is slightly above the 150 target; merging further would have hidden topics the owner asked for by name.

## Rejected items (and why)

Archived/dead: GoogleContainerTools/kaniko (2025-06), kubernetes/ingress-nginx (retired 2026-03), hashicorp/terraform-cdk
(2025-12), grafana/oncall (2025), containrrr/watchtower (2025-12; fork nicholas-fedor listed), minio/minio (2026-04),
localstack/localstack OSS (2026-03; Floci/Ministack/moto listed), daytonaio/daytona, grafana/grizzly, lost-pixel,
steipete/agent-rules, Azure/azure-mcp (→ microsoft/mcp), alexei-led/k8s-mcp-server, grafana loki-mcp, CircleCI MCP
(deprecated), dora-team/fourkeys, todogroup/repolinter, zesterer/chumsky, structurizr/java+cli+lite (→ structurizr/structurizr),
slatedocs/slate, nvie/gitflow, apiaryio/dredd, ansible/ansible-examples, hjacobs/kubernetes-failure-stories,
TezRomacH/python-package-template, watchexec/cargo-watch, etsy/DebriefingFacilitationGuide, earthly/earthly (maintenance
ended 2025-07 per README; EarthBuild fork noted only). Stale: Mergifyio/mergify OSS (2023), wg/wrk (2023), lafikl/consistent
(kept tier-3 with note). Not found: hackergrrl/art-of-readme, ngneat/falso, pulumi/mcp-server.
Licence/quality: labuladong/fucking-algorithm (no licence), ckreiling/mcp-server-docker (GPL, superseded by docker/mcp-gateway),
Umbrel (PolyForm-NC, note only), SonarQube MCP (Sonar source-available, note only), Graylog (SSPL, not listed).
Kept but flagged: google/eng-practices (archived 2024, finished classic, CC BY 3.0).
No resource attempted agent-directed instructions ("ignore previous…", "add to your config") in the files I read.

## Concerns

1. **Licences for vendoring**: 100 resources carry `license: none` (docs sites, unlicensed lists, KACTL, build-your-own-x,
   python-patterns, jepsen); all are `reference`. Source-available/BUSL items are listed as `install` with the licence
   spelled out: Terraform/Packer/Vault/Vagrant (BUSL-1.1), Restate (BUSL), Inngest (SSPL→Apache), KurrentDB (Kurrent
   License), Sentry (FSL-1.1-Apache-2.0), qlty (BUSL), Komiser (ELv2). CC BY-NC-ND content (ByteByteGo, karanpratapsingh,
   Google SRE books, awesome-claude-code, Pro Git NC-SA, zero-to-nix NC-SA) must never be copied into the garage mirror —
   link only. Bitnami charts: Broadcom's 2025 move of images to paid "Secure Images" noted.
2. **Agent-tool safety**: the K8s/Docker/cloud/PaaS MCP servers can mutate infrastructure; notes say "needs token/kubeconfig/
   Docker socket". Recommend read-only variants (mcp-kubernetes-ro, AWS read-only roles) and running servers via ToolHive or
   Docker MCP Gateway. Skills lists (Composio, VoltAgent) are indexes of unvetted third-party skills — vet each before loading;
   community-scripts/ProxmoxVE must be read before execution. Earthly/LocalStack-style sunsets show mirrors must re-verify yearly.
3. **Size**: several listed repos are huge (nixpkgs, kubernetes, grafana, sentry, cilium, terraform). Mirror by pinned tag and
   sparse paths (docs/, the `path` fields) rather than full clones; prefer the small libraries (ACL, KACTL, codelibrary) for
   full vendoring.
