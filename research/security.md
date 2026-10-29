# S5 `security` — research report (Code Garage, Phase 13)

Date: 2026-10-28. Catalog: `security.yaml` — **150 topics, 675 resources** (429 tier 1, 184 tier 2, 62 tier 3).
Verification: 13 `ghmeta.py` batches (~560 repos checked live today), ~300 non-GitHub URLs checked with `curl` (status 200 required),
12 targeted web searches for the areas most likely to have changed in 2025–26 (OWASP 2025/agentic lists, MCP/skill scanners,
Claude Code security tooling, licence changes). Nothing listed from memory alone. Boundaries respected: smart-contract security
→ `web3`, sanitizers/profilers → `systems`, general testing/CI → `engineering`, DB schema → `backend` (I kept SQLi and DB access control).

## 1. Map of the slice (area → topics)

| area | topics | what it covers |
|---|---|---|
| standards | 10 | OWASP Top 10:2025, ASVS 5.0, Cheat Sheet Series (topic map), Proactive Controls, API Top 10, MASVS/MASTG, WSTG, SAMM/SSDF, vulnerable labs, curated lists |
| lang | 8 | secure Python, Node/TS, Go, Rust, Java, C/C++, other (PHP/Ruby/.NET/Elixir), framework security guides |
| webvulns | 17 | input validation, XSS/output encoding, HTML sanitisation, CSRF, SSRF, SQLi + DB access, command injection, deserialisation, path traversal, XXE, file upload, IDOR/mass assignment, prototype pollution, ReDoS, smuggling/races/cache, SSTI, GraphQL/API |
| authn | 9 | password storage+strength, sessions, MFA/TOTP, WebAuthn/passkeys, OAuth/OIDC (RFC 9700), JWT/PASETO, self-hosted IdPs, abuse prevention (rate limits, reset flows), workload identity |
| authz | 2 | authorisation design; policy engines (OPA, Cedar, Casbin, OpenFGA, SpiceDB) |
| crypto | 9 | right answers (PQ edition), libsodium/Tink, age/minisign, per-language libs, TLS config, certificates/PKI, key management + field encryption, post-quantum, learning/testing |
| secrets | 5 | OpenBao/Vault/Infisical, sops/age/dotenvx, detection (gitleaks/trufflehog), Kubernetes secrets, leak response |
| supplychain | 11 | Renovate/Dependabot, lockfile hygiene + cooldowns, malicious packages/slopsquatting, GitHub Actions hardening, SLSA, Sigstore, SBOM, Scorecard, vuln DBs/VEX, hardened base images, trusted publishing |
| scanning | 8 | Semgrep/Opengrep, CodeQL, SCA scanners, DAST, API fuzzing, IaC + k8s manifests, Dockerfile/image scanning, orchestration/triage |
| fuzzing | 5 | native (AFL++/libFuzzer), Rust, managed languages, continuous (OSS-Fuzz/ClusterFuzzLite), learning + protocol fuzzing |
| hardening | 14 | Linux baseline, CIS/compliance automation, SSH, systemd sandboxing, fail2ban/CrowdSec, process sandboxing, Docker, container isolation, k8s cluster, k8s policy/runtime, cloud posture, cloud IAM, WAF, remote access/zero trust |
| web | 4 | security headers, CSP, CORS, cookies/HSTS/clickjacking |
| threatmodel | 5 | method (STRIDE/manifesto), tools (Threat Dragon/pytm/Threagile), attack knowledge (ATT&CK/CAPEC/CWE/ATLAS), risk scoring (CVSS4/EPSS/KEV), secure design principles |
| ops | 9 | logging, detection rules, IDS/SIEM, incident response + DFIR, disclosure/security.txt, vuln management, patching, DevSecOps pipeline, secure code review |
| privacy | 4 | privacy by design/GDPR, PII detection, anonymisation/DP/synthetic data, consent |
| offense | 12 | scope/rules of engagement, recon, content discovery, wordlists/payloads, proxies, vuln-specific tools, knowledge bases, bug bounty methodology, exploitation/password audit, reporting, CTF learning, mobile testing |
| ai | 12 | LLM Top 10, agentic threats (Agentic Top 10 2026), prompt-injection defences, runtime guardrails, red teaming, benchmarks/labs, MCP security, MCP+skill scanners, agent sandboxing, agent guard hooks, model supply chain, frameworks/governance |
| agents | 6 | Trail of Bits skills, Claude Code security review (+ official plugins), security MCP servers, offensive agents (flagged), subagents/rules collections, autonomous vuln discovery |

Every topic has a `why`, most have 1–2 sourced `practices`, and 30 resources are agent-facing (11 skills, 10 plugins, 9 MCP servers).

## 2. The 20 most valuable resources (and why)

1. **OWASP/CheatSheetSeries** (CC-BY-SA, 33.8k★, pushed today) — ~100 prescriptive how-tos; ~45 topics in this slice link to one. Vendor the `cheatsheets/` folder; it is the single best offline reference for an agent.
2. **OWASP Top 10:2025** — the new baseline (A03 Software Supply Chain Failures, A10 Mishandling of Exceptional Conditions are new; SSRF folded in). Everything maps to it.
3. **OWASP ASVS 5.0** — testable requirements with IDs; turn into acceptance criteria.
4. **trailofbits/skills** (CC-BY-SA, 7.9k★) — ~45 Claude Code plugins; the security ones (audit-context-building, differential-review, static-analysis, variant-analysis, fp-check, insecure-defaults, supply-chain-risk-auditor, agentic-actions-auditor, testing-handbook-skills, constant-time-analysis) are the best agent skills for security work that exist. Companion `skills-curated` shows the line-by-line vetting model the garage should copy.
5. **anthropics/claude-plugins-official → `claude-security` and `security-guidance`** — official in-session multi-agent scan (map/threat-model/hunt/verify/patch) and an always-on guardrail (pattern warnings + LLM diff review + commit review). Plus `anthropics/claude-code-security-review` Action and `/security-review`.
6. **Latacora "Cryptographic Right Answers: Post-Quantum Edition" (2024)** — the one page that stops agents choosing algorithms.
7. **libsodium + Tink (per-language repos)** — misuse-resistant crypto; note the Tink monorepo is archived, use `tink-go`/`tink-java`/`tink-py`.
8. **age / sops / OpenBao** — the practical secrets stack for a home server and small teams (sops+age in git; OpenBao for runtime, MPL since the Vault BUSL change).
9. **gitleaks** (MIT) + **trufflehog** (AGPL, live verification) — pre-commit and CI secret detection.
10. **Renovate + pnpm `minimumReleaseAge`** — dependency updates with a release cooldown; the single most effective control against the 2025 npm worm attacks (chalk/debug, Shai-Hulud, nx).
11. **zizmor + pinact** — GitHub Actions static analysis and SHA pinning (lesson of tj-actions/changed-files).
12. **Sigstore cosign + actions/attest-build-provenance + slsa-verifier** — signing and SLSA provenance for nearly free.
13. **syft + grype / osv-scanner / trivy** — SBOM + SCA; trivy as the all-in-one, osv-scanner for lowest noise on lockfiles.
14. **Semgrep (engine LGPL) and Opengrep** — fast SAST with custom rules; see licence concern below. `semgrep mcp` is now built into the CLI.
15. **CodeQL** — deepest dataflow SAST, free on public repos.
16. **AFL++ / cargo-fuzz / Atheris / Jazzer + ClusterFuzzLite** and the **Trail of Bits Testing Handbook (appsec.guide)** — fuzzing per language with the best practical guide.
17. **imthenachoman/How-To-Secure-A-Linux-Server + Lynis + systemd.exec sandboxing** — the home-server hardening baseline.
18. **Simon Willison's "lethal trifecta" + "Design Patterns for Securing LLM Agents" (arXiv 2506.08837) + CaMeL** — the architectural answer to prompt injection; no filter works, design does.
19. **NVIDIA/SkillSpector** (Apache-2.0, 22.9k★) and **snyk/agent-scan** (ex-Invariant mcp-scan) + **cisco mcp-scanner / skill-scanner** — scanners for exactly the artefacts the garage mirrors (skills, MCP servers). Pair with `trailofbits/mcp-context-protector` (pins tool descriptions).
20. **anthropics/sandbox-runtime + stacklok/toolhive + Claude Code sandboxing docs** — confine agents and MCP servers (filesystem + network allowlist, containers per server).

## 3. Notable agent skills, MCP servers and plugins found

- **Skills:** trailofbits/skills (45 plugins, 15+ security-specific); trailofbits/skills-curated; microsoft/hve-core `.github/skills/security/owasp-agentic` (OWASP Agentic Top 10 as a review checklist); wshobson/agents security plugins (`security-scanning`, `backend-api-security`, `frontend-mobile-security`, `security-compliance`); VoltAgent `04-quality-security` subagents (security-auditor, penetration-tester, gdpr-ccpa-compliance); github/awesome-copilot `se-security-reviewer`, `sast-sca-security-analyzer`.
- **Official Anthropic:** `claude-security`, `security-guidance` plugins; `claude-code-security-review` Action; `/security-review`; sandboxing + hooks docs.
- **Guard hooks:** Dicklesworthstone/destructive_command_guard (Rust, 6.2k★, licence file is non-SPDX — check), kenryu42/cc-safety-net (MIT).
- **MCP servers (defensive):** `semgrep mcp` (CLI built-in; standalone repo archived Oct 2025), aquasecurity/trivy-mcp, github/github-mcp-server (code-scanning/Dependabot/secret alerts), SonarSource/sonarqube-mcp-server, SocketDev/socket-mcp, trailofbits/mcp-context-protector (wrapper).
- **MCP servers (offensive, flagged reference-only):** PortSwigger/mcp-server (Burp), 0x4m4/hexstrike-ai (150+ tools), usestrix/strix (72k★ AI pentester), w0h1v/mcp-shodan (passive). cyproxio/mcp-for-security is archived.
- **Scanners for the garage itself:** SkillSpector, agent-scan, cisco mcp-scanner, cisco skill-scanner. Recommendation to the coordinator: run SkillSpector (offline mode) over every skill folder the garage mirrors, and re-run on update.

## 4. Gaps I could not fill well

- **ZAP MCP server:** search results claim an "official owasp/zap-mcp-server"; no such repo exists on GitHub (only tiny demos). Not listed.
- **Nuclei/OSV MCP servers:** only small, stale community servers (addcontent/nuclei-mcp listed as tier 3 example). Prefer Bash + explicit targets.
- **Node SSRF library:** only a 22★ package (y-mehta/ssrf-req-filter); Advocate (Python) is archived. Go (doyensec/safeurl) is the only solid library; most stacks must implement the cheat-sheet pattern by hand.
- **CSRF for Express:** csurf deprecated; csrf-csrf (196★) is the maintained option. Weak ecosystem.
- **OWASP SAMM and Top 10 Privacy Risks repos are archived**; SAMM lives at owaspsamm.org / owaspsamm/core; privacy list dropped (no maintained source).
- **"Agentic AI" and "MCP" OWASP cheat sheets do not exist yet** (404 checked); only the LLM Prompt Injection Prevention sheet.
- **Email security (SPF/DKIM/DMARC), DNS security, hardware keys (TPM/YubiKey)** — intentionally skipped as low value for the garage's audience; add later if asked.
- **Semgrep rule packs that are permissively licensed and broad:** only 0xdea (MIT, C/C++ research focus) and dgryski/semgrep-go (MIT, stale). Opengrep rules are the fallback.

## 5. Rejected or demoted items (with reason)

| item | reason |
|---|---|
| apostrophecms/sanitize-html, mozilla/bleach | archived (Feb 2026 / 2025); listed only as "migrate away" pointers → DOMPurify, nh3 |
| facebook/pyre-check (Pysa) | archived June 2026 |
| protectai/llm-guard, protectai/rebuff | archived (Jul 2026 / 2024); llm-guard kept as a tier-3 "do not pick" marker |
| Azure/PyRIT, NVIDIA/NeMo-Guardrails, Giskard-AI/giskard, microsoft/presidio, zerocore-ai/microsandbox, klaro-org/klaro, bitnami-labs/sealed-secrets, CycloneDX/cdxgen, coreinfrastructure/best-practices-badge, casbin/casbin, mozilla/ssl-config-generator, tink-crypto/tink, invariantlabs-ai/mcp-scan, BurtTheCoder/mcp-shodan, woodruffw/zizmor, cppcheck (danmar) | moved/renamed; catalog uses the new locations (microsoft/PyRIT, NVIDIA-NeMo/Guardrails, data-privacy-stack/presidio, superradcompany/microsandbox, kiprotect/klaro, bitnami/sealed-secrets, cdxgen/cdxgen, ossf/best-practices-badge, apache/casbin, tlsref/configurator, tink-crypto/tink-*, snyk/agent-scan, w0h1v/mcp-shodan, zizmorcore/zizmor, cppcheck-opensource/cppcheck) |
| semgrep/mcp | archived Oct 2025 → `semgrep mcp` CLI subcommand |
| tenable/terrascan, Shopify/kubeaudit, aquasecurity/kube-hunter, ossf/package-manager-best-practices, slackhq/goSDL, OWASP code-review guide / secure-coding quick-ref / threat-model-cookbook | archived or unmaintained; a few kept as tier-3 references where no replacement exists |
| containrrr/watchtower | archived Dec 2025; replaced by nicholas-fedor/watchtower fork + Diun (notify-only, safer) |
| daytonaio/daytona | shows archived on GitHub despite 71k★; not listed |
| pyupio/safety | no licence file; pip-audit preferred |
| osohq/oso library | archived (moved to cloud product) |
| cyproxio/mcp-for-security | archived Mar 2026; kept as a tier-3 "do not pick" marker |
| sdv-dev/SDV | Business Source License; reference only |
| HackTricks | repo has no LICENSE; site states CC BY-NC 4.0 → reference only, never vendor; also partly AI-maintained, verify commands |
| semgrep/semgrep-rules | Semgrep Rules License v1.0 (internal use only, no redistribution/SaaS) → reference, never vendor into the garage |
| trailofbits/semgrep-rules | AGPL → reference via registry |
| Burp Suite, Caido | closed source; referenced as tools, not mirrored |
| hexstrike-ai, strix | kept as reference with hard safety notes (autonomous offensive tooling); not for a shared host |
| "owasp/zap-mcp-server", FuzzingLabs/mcp-security-hub, snyk-labs/secure-at-inception | named in search results but repos do not exist / not found |

No resource attempted prompt-injection against the agent in the READMEs/SKILL.md files I read (trailofbits/skills, claude-plugins-official security plugins, snyk/agent-scan). I did not fetch SKILL.md bodies of the community subagent collections (wshobson, VoltAgent, awesome-copilot) beyond directory listings; they must be read in full before being mirrored.

## 6. Concerns

**Licences**
- Share-alike content dominates the standards area: OWASP (CC-BY-SA-4.0), trailofbits/skills (CC-BY-SA-4.0). Mirroring is fine; derivative skills must stay CC-BY-SA.
- Semgrep Rules License is the trap: engine is LGPL but the registry rules forbid redistribution. Keep rules out of any shared garage bundle; point agents at the registry or Opengrep.
- AGPL tools listed as `install` (trufflehog, Renovate, AFL++, MegaLinter, masscan, Zitadel, BunkerWeb, Teleport, buttercup): fine to run as CLIs/services, never embed.
- BUSL/non-OSS: hashicorp/vault (reference only; OpenBao is the install), SDV, SonarQube MCP (SSALv1), sysreptor community licence, brakeman (free non-commercial).
- GPL tools (hadolint, Lynis, DVWA, MobSF, acme.sh, testssl, Suricata, Wazuh): listed as tools, not vendored.
- Several repos show `NOASSERTION`/`none` in GitHub detection but carry MIT/Apache/ISC in-repo (libsodium ISC, pyotp MIT, nmap NPSL, sqlmap GPL-2.0, metasploit BSD-3, hashcat MIT); notes say which.

**Safety**
- The `agents` and `ai` areas contain things that execute: offensive MCP bundles (hexstrike, Burp MCP, nuclei-mcp), autonomous pentesters (strix), and guard hooks that run on every tool call. All carry `note` flags; `security.offense.scope-rules` and `security.agents.offensive-agents` state the authorised-scope rule. Recommendation: the garage should mark offensive items `reference` only and never auto-install them.
- Scanners for skills/MCP are necessary but all were bypassed in 2026 research (CSA, Trail of Bits); the catalog says so and pairs them with manual review and sandboxing.
- Skills/plugins that make model calls or need keys (security-guidance, agent-scan needs Snyk token, SkillSpector LLM mode, promptfoo/garak/PyRIT, oss-fuzz-gen) are flagged "needs API key" in notes.
- Vulnerable labs (Juice Shop, DVWA, DVMCP, Kubernetes Goat) must run isolated; practices say so.

**Size / mirroring**
- Large mirrors: SecLists (~1 GB), nuclei-templates, PayloadsAllTheThings, CheatSheetSeries, wycheproof, Sigma, attack-stix-data. Suggest shallow clones and excluding SecLists' `Web-Shells/` folder (contains live web shells; AV will flag it).
- Many web-only references (OWASP sites, PortSwigger Academy, MDN, Latacora) cannot be mirrored as repos; some have source repos (listed), the rest are `docs` with `use: reference`.

**Freshness**
- Fast-moving areas (MCP/skill scanners, agent sandboxes, OWASP agentic work) will need a re-check every ~3 months; stale candidates are already flagged tier 3.
