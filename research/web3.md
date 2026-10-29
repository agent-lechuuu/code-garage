# S4 `web3` — blockchains, smart contracts and their security (research report, 2026-10-28)

Catalog: `web3.yaml` — **114 topics, 500 resources** (433 unique URLs; 310 GitHub repos verified live with
`ghmeta.py`, the rest are docs/sites probed with curl). 68 sourced practices. Tier split: 307 tier-1, 159 tier-2, 34 tier-3.
Licence resolution: GitHub reported `NOASSERTION`/`none` for ~60 repos; I read each LICENSE file and wrote what I found
(BUSL-1.1, LZBL-1.2, Metaplex OSL, Reown Community License, Curve, Aptos IESCL ...). Items with no licence file say `none`.

## 1. Map of the slice (area → topics)

| area | topics | what is covered |
|---|---|---|
| evm-tooling | 13 | Foundry, fuzz/invariant testing, Hardhat 3, deploy scripts + CREATE2/3, verification, style/NatSpec, learning, gas, EVM internals, Yul/Huff, Vyper, fixed-point math, templates |
| standards | 11 | OpenZeppelin, Solady, ERC-20/721/1155, Permit/Permit2, ERC-4626, ERC-6909/7540, EIP-712/1271/6492, SIWE/SIWS, Merkle airdrops + vesting, NFT marketplaces/royalties, spec repos |
| account-abstraction | 4 | ERC-4337, EIP-7702, ERC-7579/6900 modules, Safe |
| upgradeability | 2 | proxies (transparent/UUPS/beacon, storage-layout safety), diamonds |
| defi | 12 | Uniswap v4 hooks, AMM references (EVM+Solana), lending, vault strategies, oracles, stablecoins, perps, liquidations, flash loans, MEV, data/analytics, cross-chain messaging |
| solana | 17 | Anchor, Pinocchio/native, SPL Token-2022, Metaplex, Kit/web3.js v3, Codama, local testing (Surfpool/LiteSVM/Mollusk), security pitfalls, security tools, wallets, RPC/indexing, DeFi programs, ZK compression, Jito MEV, learning/CTF, templates, Python |
| other-chains | 10 | Sui Move, Aptos Move, Cosmos SDK/IBC, CosmWasm, Bitcoin dev, Bitcoin L2/Ordinals/Lightning/BitVM, Starknet/Cairo, Polkadot/ink!, TON, NEAR/Stellar/Fuel |
| l2 | 3 | OP Stack + Base, Arbitrum/Orbit/Stylus, ZK rollups + L2BEAT |
| zk | 8 | Circom/snarkjs, Noir/Aztec, Halo2/Plonky3, zkVMs (SP1/RISC Zero/Jolt/OpenVM), Rust crypto libs, privacy apps, learning, ZK security |
| infra | 11 | viem/wagmi/ox, ethers, Alloy, Python, EVM indexers, wallet-connect UIs, explorers/decompilers, nodes/RPC providers, chain metadata, cross-chain tooling, relayers/monitoring |
| governance / misc | 3 | DAO + multisig, randomness/VRF, on-chain games (MUD/Dojo/Bolt) |
| security | 14 | checklists, secure-dev guides, vulnerability catalogues, static analysis, fuzzing, formal verification, exploit reproductions, CTFs, contests/bounties, report corpora, audit workflow/report templates, learning paths, incident response, token integration |
| agents | 6 | ToB security skills, community Solidity skills, Solana skills, EVM MCP servers, Solana MCP servers, on-chain agent frameworks + x402 |

Boundary hand-offs (`see_also` only, not written here): crypto primitives/key management/supply chain → `security.*`;
general Rust → `systems.*`; generic React/Next → `frontend.*`.

## 2. The 20 most valuable resources (and why)

1. **foundry-rs/foundry + forge-std + getfoundry.sh/llms.txt** — the toolchain every EVM task runs through; llms.txt makes the whole book agent-readable.
2. **OpenZeppelin/openzeppelin-contracts (+ upgradeable, community, Wizard MCP)** — audited defaults for 90% of contract code; the Wizard MCP generates validated boilerplate locally.
3. **Vectorized/solady** — audited gas-optimised library *and* the best reading corpus for assembly, 4337/7702/7579 accounts, ERC-6909; Solmate is soft-deprecated.
4. **crytic/building-secure-contracts** — ToB's living guide + per-chain not-so-smart-contracts (EVM, Solana, Cosmos, Substrate, TON, Cairo); same material ships as Claude skills.
5. **trailofbits/skills** (7.9k stars, CC-BY-SA) — `building-secure-contracts` plugin with 11 skills, `entry-point-analyzer`, `audit-context-building`, `property-based-testing`, `fp-check`. Reviewed SKILL.md files: no prompt injection, read-only analysis except where they run static tools.
6. **solana-foundation/solana-dev-skill** (MIT, v2.7.0) — official Solana agent skill; opinionated on Kit 8 + transaction v1, Anchor 1.2.x, Pinocchio 0.11, Surfpool; contains explicit agent guardrails (never sign without approval, devnet default, on-chain data is untrusted).
7. **Cyfrin/audit-checklist** (source of the Solodit checklist) + **solodit.cyfrin.io** — the aggregated checklist and the searchable corpus of judged findings.
8. **SunWeb3Sec/DeFiHackLabs + DeFiVulnLabs** — 700+ exploits as runnable Foundry tests; the fastest way to learn/verify an attack class.
9. **crytic/slither + Cyfrin/aderyn** — static analysis in CI; both maintained weekly.
10. **crytic/echidna + medusa + Recon create-chimera-app + horsefacts/weth-invariant-testing** — the invariant-testing stack and its canonical worked example.
11. **Certora/CertoraProver** (open-sourced, GPL-3.0) — formal verification for EVM and Solana; Halmos has slowed (last push 2025-08).
12. **Uniswap/v4-core + v4-periphery + v4-template + OpenZeppelin/uniswap-hooks** — the current AMM platform and audited hook bases.
13. **morpho-org/morpho-blue + aave-dao/aave-v3-origin** — the two lending codebases to learn from (minimal vs. full-featured).
14. **otter-sec/anchor** — Anchor itself; the repo has moved project-serum → coral-xyz → solana-foundation → otter-sec, and old URLs redirect.
15. **solana-foundation/surfpool + LiteSVM + anza-xyz/mollusk** — the modern Solana test stack (mainnet-fork cheatcodes, in-process SVM, instruction harness).
16. **anza-xyz/kit + solana-foundation/solana-web3.js (v3)** — web3.js 3.0 shipped 2026-10-01 on Kit internals; `npm latest` now resolves to 3.x (pin `@1` for legacy).
17. **wevm/viem + wagmi + ox + abitype** (all with llms.txt) — the TS stack; ethers v6 slowed (last push 2026-06).
18. **sealevel-attacks + Helius program-security guide + Neodyme pitfalls + SlowMist Solana checklist** — the Solana bug-class canon.
19. **x402-foundation/x402 + coinbase/agentkit + solana-foundation/pay** — agent payments and wallets; x402 moved to a foundation repo (6.8k stars).
20. **l2beat/l2beat + ethereum-lists/chains + ethereum/execution-apis** — trust assumptions, chain metadata and the JSON-RPC spec agents keep getting wrong.

## 3. Agent-facing resources found

**Skills (SKILL.md), reviewed for injection/safety**
- `trailofbits/skills` (plugins: building-secure-contracts [solana/cairo/cosmos/substrate/ton/algorand scanners, audit-prep, guidelines-advisor, token-integration-analyzer, code-maturity-assessor, secure-workflow-guide], entry-point-analyzer, audit-context-building, property-based-testing, differential-review, fp-check, variant-analysis). Also `trailofbits/skills-curated` (vetted community skills) and `trailofbits/claude-code-config` (sandbox/permission defaults).
- `solana-foundation/solana-dev-skill` (official), `quicknode/solana-finance-claude-plugin` (renamed from quiknode-labs/solana-anchor-claude-skill), `solanabr/ai-kit` (hub; its install.sh pulls remote packs — network), `tenequm/skills` (foundry-solidity, solana-development; declares optional PRIVATE_KEY env), `wshobson/agents` plugins/blockchain-web3 (generic), `0xlayerghost/solidity-agent-kit` (tiny, new), `greatpie/smart-contract-audit-skill` (script-driven; runs git clone + anvil), `blockscout/agent-skills`.
- None of the reviewed SKILL.md files contained instructions aimed at hijacking the agent. Flags written into `note`: runs shell / needs CLIs / optional PRIVATE_KEY / network installs.

**MCP servers**
- EVM: `mcpdotdirect/evm-mcp-server` (MIT; write ops only if `EVM_PRIVATE_KEY` set — leave unset), `PraneshASP/foundry-mcp-server` (forge/cast/anvil/heimdall; shell), `OpenZeppelin/openzeppelin-mcp` + `contracts-wizard/packages/mcp` (`@openzeppelin/contracts-mcp`, local or mcp.openzeppelin.com; Solidity/Cairo/Stylus/Stellar/Sui/Uniswap hooks), `blockscout/mcp-server` (read-only, custom licence), `alchemyplatform/alchemy-mcp-server` (API key).
- Solana: `solana-foundation/solana-mcp` (official, hosted mcp.solana.com — docs RAG + `program_autofixer`; CLI `npx @solana/mcp` needs no key), `sendaifun/solana-mcp` (needs private key for actions; stale 2025).
- No maintained official Foundry MCP from Paradigm exists; Foundry's llms.txt + the PraneshASP server is the practical pair.

**llms.txt endpoints verified (HTTP 200, text/plain)**
getfoundry.sh, viem.sh, wagmi.sh, oxlib.sh, abitype.dev, hardhat.org, docs.openzeppelin.com, docs.uniswap.org, docs.chain.link,
docs.layerzero.network, wormhole.com/docs, docs.hyperlane.xyz, docs.across.to, docs.morpho.org (+llms-full), aave.com/docs, docs.gmx.io,
ponder.sh, docs.envio.dev, docs.sqd.dev, rainbowkit.com, docs.reown.com, docs.privy.io, docs.dynamic.xyz, portal.thirdweb.com,
docs.safe.global, docs.pimlico.io, docs.zerodev.app, docs.metamask.io, docs.ens.domains, docs.scaffoldeth.io, speedrunethereum.com,
docs.optimism.io, docs.arbitrum.io, docs.base.org, docs.cdp.coinbase.com, docs.starknet.io, docs.aztec.network, docs.sui.io, aptos.dev,
developers.metaplex.com, docs.helius.dev, surfpool.run, docs.solanamobile.com, docs.squads.so, zkcompression.com, docs.drift.trade, docs.jup.ag,
docs.pyth.network, alloy.rs, alchemy.com/docs, quicknode.com/docs, docs.chainstack.com, docs.blockscout.com, docs.etherscan.io, docs.tenderly.co, docs.cyfrin.io.
**Missing (404)**: anchor-lang.com, docs.soliditylang.org, noir-lang.org, docs.succinct.xyz, dev.risczero.com, docs.flashbots.net, docs.zksync.io,
docs.scroll.io, docs.certora.com, docs.ethers.org, solanakit.com, codama.dev, mud.dev. **Unprobeable**: solana.com (429 rate-limit for scripted
fetches — use the Solana MCP), docs.circom.io / docs.switchboard.xyz / trident.ackee.xyz (connection refused to curl).

## 4. Renames and moves found today (training knowledge is wrong on these)

| old | now | note |
|---|---|---|
| ethereum/solidity, solc-js, hevm, sourcify | **argotorg/** | Argot Collective took over in 2025 |
| ethereum/remix-project | remix-project-org/remix-project | |
| ethereum/web3.py | **ApeWorX/web3.py** | |
| coral-xyz/anchor, solana-foundation/anchor | **otter-sec/anchor** | OtterSec maintains Anchor |
| solana-labs/solana-web3.js | solana-foundation/solana-web3.js (v3) | anza-xyz/kit is the Kit |
| solana-labs/wallet-adapter | anza-xyz/wallet-adapter | legacy; Wallet Standard + @solana/react for new apps |
| txtx/surfpool | solana-foundation/surfpool | |
| solana-developers/program-examples, create-solana-dapp | solana-foundation/* | templates in solana-foundation/templates |
| Ellipsis-Labs/solana-verifiable-build | solana-foundation/solana-verifiable-build | |
| buffalojoec/mollusk | anza-xyz/mollusk | |
| metaplex-foundation/kinobi | codama-idl/codama (successor) | kinobi still exists |
| solana-labs/solana-program-library | **archived**; per-program repos under solana-program/ | |
| solana-labs/solana | archived; anza-xyz/agave | |
| solana-labs/solana-pay | solana-foundation/pay (now an x402/MPP/AP2 CLI) | |
| safe-global/safe-smart-account, safe-modules | **safe-fndn/** | safe-core-sdk still under safe-global |
| smartcontractkit/ccip | archived; **smartcontractkit/chainlink-ccip** | |
| pyth-network/pyth-sdk-solidity | archived; `pyth-crosschain/target_chains/ethereum/sdk/solidity` | |
| aave/aave-v3-core | archived; aave-dao/aave-v3-origin | aave/gho-core archived too |
| drift-labs/protocol-v2 | velocity-exchange/protocol-v2, **archived 2026-07** | after the April-2026 exploit |
| mrgnlabs/marginfi-v2 | 0dotxyz/marginfi-v2 | |
| Consensys/linea-monorepo | LFDT-Lineth/lineth-monorepo | LF Decentralized Trust |
| OffchainLabs/arbitrum-orbit-sdk | arbitrum-chain-sdk; cargo-stylus archived | |
| Consensys/mythril, smart-contract-best-practices | ConsenSysDiligence/* | |
| solana-labs/security-audits | anza-xyz/security-audits | |
| huff-language/huff-rs | **archived**; cakevm/huff-neo | |
| rhinestonewtf/modulekit | **archived 2026-09**; core-modules + module-sdk | web results still call it current |
| ithacaxyz/porto | archived 2026-08; ithacaxyz/account remains | |
| coinbase/x402 | x402-foundation/x402 | coinbase repo is now a fork |
| smlxl/evm.codes | duneanalytics/evm.codes | |
| mds1/multicall | mds1/multicall3 | |
| sablier-labs/lockup | sablier-labs/evm-monorepo | |
| coinbase/onchainkit | **archived 2026-09** | use docs.base.org |
| Synthetixio/synthetix-v3, balancer/balancer-v3-monorepo, 0xPolygonZero/plonky2, move-language/move | archived | |

## 5. Gaps I could not fill well

- **Official Foundry MCP**: none; community servers are small (PraneshASP 255★, pushed 2026-01). Foundry's llms.txt is the reliable agent surface.
- **Perps**: Synthetix v3 archived, Drift archived, Hyperliquid closed; only GMX v2 (BUSL) and dYdX v4 remain as open references.
- **Solana static analysis**: all tools are small (x-ray 57★ AGPL, radar 154★ GPL, l3x stale, crytic/solana-lints archived). Trident is the only maintained fuzzer.
- **Solana governance (Realms/spl-governance)**: Mythic-Project repos are tiny and unlicensed; left out, Squads v4 covers multisig.
- **Permissive liquidation bots**: morpho-org bot archived; Compound's lives inside a BUSL repo.
- **Solana docs for agents**: solana.com blocks scripted fetches (429) and has no reachable llms.txt; the official Solana MCP is the workaround.
- **ZK learning lists** are stale (awesome-zk 2024, awesome-zkp archived); zkdocs, RareSkills ZK Book and the MOOC carry the topic.
- **Token launch / bonding curves**: only Meteora DBC (noncommercial licence); pump.fun-style code is closed.

## 6. Rejected (with reason)

- `goat-sdk/goat` — README says "[Archived] read-only snapshot"; replaced by coinbase/agentkit, x402.
- `vybenetwork/solana-mcp-vybe` — 2.2k stars on a "registry metadata" repo with no licence; star count inconsistent with content → likely promotional, not listed.
- `mukul975/Anthropic-Cybersecurity-Skills` — 35k stars, 817 auto-generated skills under a name that impersonates Anthropic; not an Anthropic project. Excluded (brand impersonation, unreviewable volume).
- `tenequm/claude-plugins foundry-solidity` — flagged "Obfuscated File" by Socket in search results; the successor `tenequm/skills` foundry-solidity SKILL.md was read in full (9.4 KB, no encoded content) and listed tier 2 instead.
- `honey-guard/solana-fender`, `VulnPlanet/l3x`, `otter-sec/solana-ctf` (404), `Microck/rr-solidity` (404), `Quillhash/QuillAudit-Auditor-Roadmap` (404), `neodyme-labs/solana-security-workshop` (404) — not found or too small.
- `trailofbits/manticore`, `crytic/etheno`, `crytic/not-so-smart-contracts`, `Picodes/4naly3er` (2024), `flashbots/mev-share` (2023) — archived or stale; superseded by listed tools.
- `foundry-rs/forge-template`, `NomicFoundation/hardhat-ignition`, `boundless-xyz/risc0-foundry-template`, `stackup-wallet/stackup-bundler`, `base/node`, `0xPolygon/cdk` — archived.
- `WTFAcademy/WTF-Solidity` — fork; replaced with canonical `AmazingAng/WTF-Solidity` (14k★).
- Hosted-only products without open code or llms.txt (Hyperliquid, pump.fun, Phantom wallet SDK) — nothing to mirror.
- No resource attempted prompt injection in the files I read (ToB, Solana Foundation, QuickNode, tenequm, solanabr, 0xlayerghost, greatpie, wshobson SKILL.md heads; 4 MCP READMEs).

## 7. Concerns

**Licences (the big one for `vendor`)**
- BUSL-1.1 is everywhere in DeFi: Uniswap v3/v4-core (v4 has no root LICENSE, only SPDX headers), Aave v3, Compound III, Euler EVK, GMX, Kamino, RedStone, Across, Liquity v2, Arbitrum Nitro, Dune Spellbook, Sablier, RareSkills exercises. All marked `reference`, never `vendor`.
- Business/community licences: LayerZero (LZBL-1.2), Reown AppKit (Community License since 2025-08), Metaplex programs (Metaplex OSL), Orca Whirlpools (restrictive since 2025-02), Curve (Swiss Stake), Meteora (noncommercial), Aptos (Innovation-Enabling licence replaced Apache-2.0), Blockscout MCP (LicenseRef-Blockscout).
- AGPL on tools is fine to *run* (Slither, Echidna, Medusa, OZ Relayer/Monitor, Yearn, Squads, CreateX) but not to vendor into closed code; noted per resource.
- Non-commercial CC: Decurity semgrep rules, OWASP SC Top 10. Many checklists/report corpora have **no licence file** (Cyfrin audit-checklist, SCSVS, pashov, spearbit, sealevel-attacks, weird-erc20, solana-mcp, kernel, hyperindex, chimera). Mirroring them locally is a grey area; listed as `reference`.

**Safety**
- Chain MCP servers and several skills accept `PRIVATE_KEY`/`EVM_PRIVATE_KEY`; the catalog says to leave it unset and run read-only. `sendaifun/solana-mcp` needs a key for anything useful → tier 3.
- `solanabr/ai-kit` install.sh and `greatpie` scripts fetch/clone remote code at runtime; review before enabling.
- Skills marketplaces with thousands of stars (`wshobson/agents`, `mukul975/*`) are too large to review; only the `blockchain-web3` plugin of wshobson is listed, mukul975 is rejected.

**Size / mirroring**
- Monorepos are huge: solana `agave`, `aptos-core`, `MystenLabs/sui`, `paritytech/polkadot-sdk`, `ethereum-optimism/optimism`, `AztecProtocol/aztec-packages`, `smartcontractkit/chainlink` (multi-GB with history). Mirror with `--depth 1` and only the `path` given where one is set.
- The exploit corpora (DeFiHackLabs) need archive-node RPC URLs to run; the tests themselves are small.

**Freshness**
- Several classics are finished and intentionally old (Uniswap v2, sealevel-attacks, solcurity, EVM puzzles, Secureum mind map); their `note` says so. Everything else was pushed within the last 12 months except where flagged (ethers.js 2026-06, Halmos 2025-08, Permit2 2024-08, mev-share-client-ts 2024-05, Artemis 2024-03).
