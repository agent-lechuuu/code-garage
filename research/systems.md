# S3 `systems` — report (2026-10-28)

Catalog: `systems.yaml` — 150 topics, 714 resources, 21 areas, 81 sourced practices on 46 topics.
Method: ~900 GitHub repos checked live with `ghmeta.py` (licence, stars, last push, archived), ~250 non-GitHub URLs probed
for liveness, LICENSE files read for every repo GitHub reported as none/NOASSERTION (licence written as found),
READMEs/SKILL.md/instruction files read for every MCP server, skill and plugin listed. Nothing listed from memory alone.
Topic ids follow `systems.<area>.<topic>`; `see_also` to other slices uses guessed ids (`security.*`, `engineering.*`,
`backend.*`, `frontend.*`, `ai.*`, `iot.*`). Generator and verified metadata cache: scratchpad `sys/` (gen.py, t1–t4.py, *.jsonl).

## Map (area → topics)

| area | n | topics |
|---|---|---|
| c | 5 | modern-c, safe-strings-memory, single-header-libs, sanitizers, testing |
| cpp | 9 | core-guidelines, modern-features-learning, foundation-libs, fmt-logging, testing, static-analysis-tooling, json-serialization, async-networking, package-management-templates |
| rust | 11 | learning, idioms-api-guidelines, error-handling, async-tokio, unsafe-miri, serde, rayon-crossbeam, tracing, performance-data-structures, testing-cargo-tooling, ffi-and-proc-macros |
| go | 6 | idioms-style, concurrency, project-layout-learning, testing, linting-tooling, performance-pprof |
| langs | 3 | zig, nim-odin, assembly (x86-64/ARM64/RISC-V) |
| memory | 3 | allocators-and-gc, arena-allocators, hardware-model-layout |
| concurrency | 6 | atomics-memory-ordering, lock-free-queues-rcu, actor-models, thread-pools-task-graphs, coroutines-fibers, race-detection-model-checking |
| perf | 15 | foundations-mechanical-sympathy, cache-friendly-data-oriented-design, simd, cpu-microarch-branch-prediction, zero-copy-serialization, io-uring-zero-copy-io, epoll-event-loops, kernel-bypass-userspace-stacks, hft-low-latency-practices, latency-measurement, low-latency-linux-tuning, messaging-ipc-low-latency, fast-hashing-hashmaps, fast-parsing-strings-compression, compiler-optimization-pgo-lto |
| profiling | 6 | perf-flamegraphs, ebpf-bpftrace, memory-profilers, frame-trace-profilers, microbenchmarks, debuggers-gdb-lldb-rr |
| net | 7 | sockets-fundamentals, tcp-tuning, quic-http3, packet-capture-analysis, http-parsers-servers-low-level, load-generators-bandwidth, xdp-ebpf-datapath |
| os | 7 | textbooks-courses, writing-an-os, linux-kernel-development, linux-system-programming-api, virtualization-kvm, container-internals, filesystems-fuse |
| embedded | 11 | rust-embassy-hal, zephyr, freertos-other-rtos, esp-idf-arduino-platformio, c-hals-cmsis-vendor, debug-test-simulation, micropython-circuitpython-tinygo, iot-protocols-mqtt-coap-can, linux-yocto-buildroot-ota, raspberry-pi-gpio-pico, learning-lists |
| compilers | 9 | crafting-interpreters-small-compilers, courses-ir-ssa, llvm-backends-jit, tree-sitter-ast-grep, parser-combinators-generators, regex-engines, embeddable-scripting-engines, linkers-elf, binary-parsing-disassembly |
| wasm | 5 | runtimes-plugins, wasi-component-model, rust-wasm-bindgen, c-cpp-emscripten-toolchain, spec-learning-other-languages |
| gpu | 7 | cuda-fundamentals, cuda-libraries-rust-bindings, triton-kernels, wgpu-webgpu-shaders, vulkan-opengl-graphics, portable-compute-frameworks, profiling-nsight-nvtop |
| shell | 10 | bash-strict-mode-pitfalls, bash-idioms-references-cheatsheets, shellcheck-shfmt-shellharden, testing-bats (incl. CLI testing), style-guides, posix-sh-portability, cli-frameworks-interactive, zsh-fish-nushell, awk-sed-text-processing, jq-yq-structured-data |
| linux | 12 | systemd-units-hardening, systemd-timers-scheduling, daemons-sd-notify-dbus, kernel-tuning-sysctl-cgroups, troubleshooting-performance-logs, network-admin-iproute2-nftables, filesystems-storage-admin, packaging-deb-rpm, references-handbooks, modern-cli-replacements, shell-productivity-dotfiles, monitoring-tui |
| cli | 4 | design-guidelines-config, argument-parsing-libraries, tui-frameworks-terminal-output, cross-compilation-distribution |
| build | 7 | make-task-runners, cmake, ninja-meson-others, bazel-buck2, nix-reproducible, compilation-caching-speed, compile-commands-clangd |
| style | 2 | style-guides-formatters, api-docs-doxygen-mdbook |
| agent | 5 | lsp-semantic-code-tools, per-language-mcp-servers, shell-linux-mcp, debugging-mcp, rules-subagents-skills-systems |

The owner's explicit ask ("high/low latency coding practices") is covered by the perf area (15 topics) plus
concurrency.lock-free, memory.*, profiling.*, net.tcp-tuning and linux.kernel-tuning; each perf topic carries sourced practices.

## The 20 most valuable resources (and why)

1. **Algorithms for Modern Hardware** (en.algorithmica.org/hpc) — free, measured, whole-stack performance book; the best single entry point.
2. **Performance Analysis and Tuning on Modern CPUs** (dendibakh/perf-book, + perf-ninja labs) — the practitioner's methodology (TMA, perf, PGO) with exercises.
3. **Erik Rigtorp's Low Latency Tuning Guide** — the concise checklist for isolating cores, IRQs, THP, governors; pairs with Red Hat's RHEL 9 Real Time guide.
4. **Carl Cook, "When a Microsecond Is an Eternity"** + David Gross "Trading at light speed" — the two HFT talks that define hot-path practice.
5. **HdrHistogram (C/Rust) + Gil Tene "How NOT to Measure Latency"** + wrk2 — correct latency measurement; coordinated omission explained and solved.
6. **liburing + Lord of the io_uring + Axboe's networking-2023 wiki** — the complete io_uring path from tutorial to production patterns.
7. **Google Highway** — portable SIMD with runtime dispatch; the right default for vectorized C++ (xsimd/SIMDe as alternatives).
8. **Rust Atomics and Locks** (free online + any-use code) — clearest treatment of memory ordering; useful for C++ too.
9. **rigtorp/awesome-lockfree + moodycamel::ConcurrentQueue + SPSCQueue** — curated theory plus vendorable queues.
10. **C++ Core Guidelines + GSL + cppreference** — the review standard for C++.
11. **Rust API Guidelines + Rust Performance Book + Effective Rust** — the three documents that make Rust code idiomatic and fast.
12. **Tokio + tutorial + mini-redis** — reference async stack and a copyable server skeleton.
13. **Serena + the official Claude Code LSP plugins (clangd/rust-analyzer/gopls)** — IDE-grade semantics for agents across Rust/C/C++/Go/Zig/Bash.
14. **bpftrace + BCC + libbpf-bootstrap + bpf-developer-tutorial** — observe anything on Linux without recompiling.
15. **perf + FlameGraph + Hotspot + samply + Tracy** — CPU profiling from one-liners to nanosecond frame timelines.
16. **BashPitfalls + BashFAQ/105 + ShellCheck (+ wiki) + shfmt + Bats** — the complete "correct Bash" toolchain.
17. **systemd.exec(5) + systemd-analyze security + shh** — hardened service units generated from real syscall traces.
18. **tldr-pages** (CC-BY-4.0, vendorable) + cheat.sh — offline command examples for agents.
19. **Wasmtime + Component Model book + wasm-tools** — the standards-track Wasm stack for plugins/sandboxes.
20. **Embassy + embedded-hal + Zephyr** — the two modern firmware stacks (Rust async, vendor-neutral C RTOS).

Honourable mentions: simdjson/fast_float/memchr (fast primitives), mold (linking), clig.dev (CLI design), OSTEP + xv6-riscv,
Crafting Interpreters + chibicc, tree-sitter + ast-grep, DPDK + Seastar + AF_XDP docs, github/awesome-copilot instruction files.

## Agent-facing resources found (skills, MCP servers, plugins)

- **anthropics/claude-plugins-official** (Apache-2.0): `plugins/clangd-lsp`, `plugins/rust-analyzer-lsp`, `plugins/gopls-lsp` — official LSP wiring; also `serena` under `external_plugins`. Requires the language server binaries locally.
- **oraios/serena** (app GPL-3.0, SolidLSP MIT): LSP-backed symbol tools for 40+ languages incl. Rust, C/C++, Go, Zig, Bash. Spawns local language servers; no network needed.
- **isaacphi/mcp-language-server** (BSD-3), **ProfessioneIT/lsp-mcp-server** (MIT): generic LSP→MCP bridges.
- **ast-grep/ast-grep-mcp** (MIT): structural search/rewrite; local only.
- Per language: **zeenix/rust-analyzer-mcp** (MIT), **nuskey8/docs-rs-mcp** (MIT, network), **felipeerias/clangd-mcp-server** (MPL-2.0, needs compile_commands.json), **xieyuschen/gopls-mcp** (BSD-3; installer script downloads a binary), **Govcraft/rust-docs-mcp-server** (MIT; needs an OpenAI key for embeddings).
- Shell/SSH/terminal (all execute arbitrary commands; listed tier 2–3 with warnings): **wonderwhy-er/DesktopCommanderMCP** (MIT, 10k stars), **g0t4/mcp-server-commands** (MIT), **tufantunc/ssh-mcp** (MIT), **classfang/ssh-mcp-server** (ISC; command allow/deny lists; in the official servers list), **ferodrigop/forge** (MIT; PTY sessions).
- Debugging (tier 3, small projects): **stass/lldb-mcp** (BSD-2, quiet since 2025-03), **yywz1999/gdb-mcp-server** (MIT; attaches to gdb in tmux; README in Chinese), **Benestar/godbolt-mcp** (MIT; network), **sameehj/ebpf-mcp** (Apache-2.0; needs root).
- Skills / rules: **github/awesome-copilot** `instructions/{rust,go,shell,cmake-vcpkg,performance-optimization}.instructions.md` (MIT; well-sourced, adaptable to CLAUDE.md); **wshobson/agents** `plugins/systems-programming` (c-pro, cpp-pro, rust-pro, golang-pro + skills memory-safety-patterns, rust-async-patterns, go-concurrency-patterns), `plugins/shell-scripting` (bash-defensive-patterns, bats-testing-patterns, shellcheck-configuration), `plugins/debugging-toolkit`, `plugins/arm-cortex-microcontrollers` (MIT); **VoltAgent/awesome-claude-code-subagents** `categories/02-language-specialists/{rust-engineer,cpp-pro,golang-pro}.md`, `07-specialized-domains/embedded-systems.md` (MIT; generic checklists); **PatrickJS/awesome-cursorrules** (CC0); **agentsmd/agents.md** (MIT).
- Injection check: none of the SKILL.md / instruction / README files read contained instructions aimed at agents beyond their stated purpose. The `gopls-mcp` and several MCP READMEs recommend `curl … | bash` installers — normal, but flagged as "fetches a binary" in notes.
- Not found: no credible MCP/skill for shellcheck, systemd, journalctl, man pages, valgrind, perf/flamegraphs, CMake (0–3-star experiments only). `anthropics/skills` has no systems-related skill; the big "awesome-claude-skills" lists have nothing systems-specific.

## Gaps I could not fill well

- **Rust proc-macro references**: only dtolnay's workshop (merged into the FFI topic); the "Little Book of Rust Macros" was not verified in time.
- **No vendorable, permissively licensed "low-latency practices" document** exists: penberg/awesome-low-latency, rigtorp/awesome-lockfree, 0burak/imperial_hft, MattPD/cpplinks, dbartolini/data-oriented-design and perf-ninja carry **no licence file** — link and read, do not mirror.
- **Timekeeping/TSC**: only linuxptp + chrony (in the low-latency-tuning topic); no good standalone TSC/clock_gettime guide was verified.
- **Shell portability**: Rich Felker's "sh tricks" (etalabs.net) was unreachable; POSIX spec + autoconf chapter + pure-sh-bible cover it.
- **Memory layout**: ESR's "Lost Art of Structure Packing" (catb.org) was unreachable from the server; Drepper's paper covers the ground.
- **Zig** is pre-1.0 and ziglings moved to Codeberg; the GitHub mirror (ziglings-org/exercises) is a 49-star shadow, so the Codeberg URL is listed.
- **GPU**: this server's GTX 1650 Ti (Turing, sm_75) is supported by CUDA 13 (Maxwell/Pascal/Volta were dropped) but community sources report Triton ≥ 3.3 dropped Turing and bf16 never worked there — noted in the topic; could not confirm from an official Triton page.
- **Nim/Odin** got one shared topic; nothing agent-specific exists for them.

## Rejected or demoted items (reason)

Archived (not listed): agarrharr/awesome-cli-apps; AlexEne/twiggy (ex-rustwasm); zesterer/chumsky (archived 2026-03); zigzap/zap (http.zig
listed instead); golemparts/rppal (linux-embedded-hal instead); dirs-dev/dirs-rs and directories-rs (etcetera instead); knurling-rs/probe-run
(probe-rs); golang/mock (uber-go/mock); bytecodealliance/cranelift (now inside wasmtime, listed by path); facebookarchive/BOLT (now llvm-project/bolt);
google/orbit; blackmagic-debug/blackmagic; gurugio/lowlevelprogramming-university (also GPL); ferrous-systems/teaching-material; cpp-best-practices/
gui_starter_template; rust-vmm/kvm; learnbyexample/Command-line-text-processing (per-tool books listed); osdev0/wiki; pmem/pmdk; weidwonder/terminal-mcp-server.
Archived but kept with a note (finished classics): dylanaraps/pure-bash-bible and pure-sh-bible (2023), rustwasm/book (Aug 2025).
Stale but kept as finished classics (34 resources, each noted): FlameGraph, wrk/wrk2, craftinginterpreters, chibicc, too-many-lists, go-perfbook,
cppcoro, libdill, libco, ixy, bocker, ostep-projects, greatest, interactive_latencies, modern-unix, art-of-command-line, getoptions, LearnOpenGL,
olcf/cuda-training-series, GPU-Puzzles, Essentials-of-Compilation, ssabook, awesome-compilers, RapidJSON, termshark, cargo-bloat (note only), ClangBuildAnalyzer, lldb-mcp.
Dead/unreachable URLs dropped: usenix "login" article (404), Red Hat RHEL 9 low-latency blog (404; replaced by the RT documentation, verified via fetch),
copyconstruct "method to epoll's madness" (403), etalabs sh_tricks and catb.org structure-packing (no response), sed1line.txt (404).
Sites that block automated clients but exist (listed with a note): OSDev wiki (403), Intel Intrinsics Guide (403), docs.redhat.com (403 to curl, verified via WebFetch).
Not listed on quality/fit: golang-standards/project-layout kept only as tier 3 with a warning (contested, "Hacker license"); hesreallyhim/awesome-claude-code
(CC-BY-NC-ND, general → S6); ComposioHQ/travisvn/BehiSecc awesome-claude-skills (no licence, nothing systems-specific); cameron314/readerwriterqueue (licence
not read, concurrentqueue covers it); Mbed OS (Arm EOL July 2026, maintenance stopped); powerlevel10k (project in "very limited support" mode → starship);
0–3-star MCP servers for gdb/cmake/cargo/crates.io; appcypher/awesome-wasm-runtimes (stale 2024, no licence); kahun/awesome-sysadmin (stale, → S6).
Out of slice, referenced only via see_also: pwndbg/GEF-style exploitation workflows, fuzzing (security); Docker/k8s/Cilium operation, goreleaser, k6,
observability backends, continuous profiling (engineering); axum/actix-web/gRPC (backend); ESPHome/Home Assistant (iot); CUDA ML kernels, cuDNN, FlashInfer (ai).

## Concerns

1. **Safety of agent tooling.** Every item in `systems.agent.shell-linux-mcp` and `systems.agent.debugging-mcp` executes arbitrary commands,
   several need SSH credentials or root, and most are small (<1k stars). Keep them out of any default install; prefer the built-in Bash tool;
   if adopted, use command allowlists and never put secrets in prompts. All are marked in `note`.
2. **Licences.** 70 resources are GPL-family (tools like ShellCheck, golangci-lint, Cppcheck, Doxygen, Hotspot, Wireshark, kernel/man docs):
   fine to install and read, never `vendor`. 14 resources are CC-BY-NC (Modern C, Beej's guides, Crafting Interpreters text, cppbestpractices,
   0xAX, linux-insides, Build Your Own Lisp, LearnOpenGL, 100 Go Mistakes, cliutils Modern CMake): reference only, no redistribution.
   ~20 high-value lists/notes have **no licence** (penberg, rigtorp, cpplinks, dbartolini, perf-ninja, imperial_hft, blessed.rs, xdp-tutorial,
   picohttpparser root): link, do not mirror. Dual/complex licences were written as found (zstd BSD/GPL, xxHash lib/cli, libbpf LGPL/BSD, Serena GPL/MIT).
3. **Mirror size and churn.** llvm-project, torvalds/linux, nixpkgs, QEMU, Zephyr, ESP-IDF, DPDK, Boost, CUTLASS are multi-GB monorepos:
   mirror only the `path`/docs that matter or pin a tag. Fast-moving items: Zig (pre-1.0), Triton/CUDA GPU-architecture support, MCP servers
   (five repos were renamed in the last months: youki-dev, wasm-bindgen org, bashly-framework, wild-linker, gpu-mode/Triton-Puzzles, chelsea0x3b/cudarc).
4. **Hardware specifics.** GPU topics assume the server's Turing GTX 1650 Ti: CUDA 13 works, sm_75 only, no bf16; Triton use is risky
   (community reports support dropped at 3.3). Low-latency tuning practices (isolcpus, performance governor, THP off) are for dedicated
   boxes — do not apply them to this shared home server without a reason.
5. **Bot-blocked sources.** Three listed sites return 403 to automated fetchers (OSDev wiki, Intel Intrinsics Guide, docs.redhat.com);
   an agent must open them in a browser tool or accept a human-provided copy.
