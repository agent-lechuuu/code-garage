# S2 `backend` — research report (2026-10-28)

Catalog: `backend.yaml` — **150 topics, 736 resources** (619 unique GitHub repos + ~115 docs/guides/specs/sites), 11 areas.
Every GitHub repo was verified live with `ghmeta.py` today (licence, stars, last push, archived) and re-verified in a
final pass over the finished file: 0 not-found, 0 licence/archived mismatches, 0 unresolved renames. Every non-GitHub
URL (RFCs, Postgres docs, blog posts, llms.txt files) was checked with `curl -I` (all 200; 7 dead links dropped).
Two forked sub-tasks were used: (a) agent-facing resources (MCP servers, skills, plugins, llms.txt), (b) 2025–2026
status changes (renames, relicensing, acquisitions, archivals). Their findings are folded into `note` fields.

## 1. Map of the slice (area → topics)

| area | topics | what it covers |
|---|---|---|
| runtimes | 19 | Node/TS, Bun/Deno, Python (+ASGI), Go, Rust, JVM, Elixir, .NET, PHP, Ruby frameworks; validation (TS + polyglot), config/env, DI, fast JSON, server templates + htmx, HTTP clients + resilience, edge/serverless |
| api | 24 | REST guidelines, OpenAPI (spec/lint/diff, client codegen, server-first TS + polyglot, docs UIs), mocking, testing clients, RFC 9457 errors, pagination, versioning, idempotency keys, rate limiting, GraphQL, Postgres-as-API, gRPC/Connect, typesafe TS RPC, WebSockets, SSE, webhooks, gateways, feature flags, sync engines, IDLs |
| auth | 12 | OAuth/OIDC libs, app auth (TS + polyglot), sessions vs JWT, passkeys, self-hosted IdPs, forward-auth proxies, authz engines, in-app permissions, multi-tenancy, API keys, password hashing/TOTP |
| jobs | 11 | queues per language (4), Postgres-as-queue, durable workflows, scheduling/cron, brokers, broker clients, outbox/messaging frameworks, event sourcing |
| services | 21 | Redis clients/patterns/compatible stores, in-process + HTTP caching, S3 servers + clients, uploads, media, documents, email (send/templates/self-host), Stripe, billing platforms, notifications, search engines/libraries/Postgres FTS, vector DBs, geospatial |
| databases | 18 | Postgres core/extensions/partitioning/platforms, BaaS, SQLite (core/drivers/replication), DuckDB, ClickHouse+OLAP, time-series, MongoDB/document, MySQL/MariaDB, distributed SQL, graph, embedded KV, GUIs/CLIs, schema diagrams |
| orm | 7 | TypeScript ORMs, Node PG drivers/typed SQL, Python, Go, Rust, JVM/.NET, Ruby/PHP/Elixir |
| safe-db | 23 | **owner priority**: zero-downtime migration rules, migration linters, runners, declarative/online schema tools, indexing, query plans, isolation, locking, pooling, backups/PITR, replication/HA, RLS + roles, data modelling, soft deletes/audit, identifiers (UUIDv7), money/time, review checklists, SQL lint/parse, DB testing, seed/anonymise, monitoring/tuning, vacuum/upgrades, bulk loading |
| data-eng | 8 | dataframes/query engines, dbt/SQLMesh + quality, orchestration, stream processing, CDC, ingestion/ELT, formats + serialization, BI |
| starters | 3 | Python/TS starters + best-practice lists; Go/Rust/JVM/.NET templates; SaaS boilerplates + RealWorld |
| agents | 4 | database MCP servers, framework MCP servers/toolkits, backend agent skills, plugin packs/rules/llms.txt |

Tier split: ~57% tier 1, ~36% tier 2, ~7% tier 3. `practices` (sourced rules, ≤5 per topic) are present on 58 topics,
densest in safe-db and api.

## 2. The 20 most valuable resources (and why)

1. **supabase/agent-skills → skills/supabase-postgres-best-practices** (MIT) — the best ready-made SKILL.md for Postgres: schema, index, RLS and security rules that apply to any Postgres; drop-in for every project.
2. **timescale/pg-aiguide** (Apache-2.0) — skills for table design, migrations, pgvector, hybrid search, PostGIS plus an MCP that searches the Postgres manual; the second Postgres skill pack to pin.
3. **sbdchd/squawk** (Apache-2.0) — language-agnostic migration-safety linter with GitHub Action; its rule docs double as the schema-review checklist the owner asked for.
4. **postgres.ai "Common DB schema change mistakes" + Braintree "Safe operations"** — the two guides every zero-downtime rule derives from; cite them in CLAUDE.md.
5. **ariga/atlas** (Apache-2.0) — schema-as-code, lint, drift detection, and ships its own agent skill (`skills/atlas`).
6. **xataio/pgroll** (Apache-2.0) — automated expand/contract zero-downtime Postgres migrations.
7. **crystaldba/postgres-mcp, bytebase/dbhub, googleapis/mcp-toolbox** (MIT/MIT/Apache) — the three DB MCP servers with read-only modes; MCP Toolbox's parameterised-SQL `tools.yaml` is the safest pattern.
8. **honojs/hono** (MIT) — default TS framework on every runtime, with `llms-full.txt`.
9. **fastapi/fastapi + fastapi/full-stack-fastapi-template** (MIT) — default Python API stack and its official template.
10. **drizzle-team/drizzle-orm, prisma/orm (v7/8), kysely-org/kysely** — the TS data layer; all three publish llms.txt.
11. **sqlc-dev/sqlc + jackc/pgx** (MIT) — the Go SQL default (typed SQL, no reflection).
12. **better-auth/better-auth** (MIT) — TS auth framework that absorbed Auth.js stewardship; llms.txt + official skills.
13. **keycloak/keycloak, goauthentik/authentik, pocket-id/pocket-id** — self-hosted SSO from heavy to tiny (Pocket ID is passkey-only, ideal for one household).
14. **openfga/openfga + authzed/spicedb** (Apache-2.0) — Zanzibar-style authorization when roles outgrow if-statements.
15. **riverqueue/river, timgit/pg-boss, procrastinate, pgmq** — Postgres-backed queues (no Redis) with transactional enqueue.
16. **temporalio/temporal, hatchet-dev/hatchet, dbos-inc/dbos-transact-py** (MIT) — durable workflows from heavy to library-only.
17. **valkey-io/valkey** (BSD-3) — the Redis replacement after the 2025 relicensing.
18. **deuxfleurs-org/garage + seaweedfs/seaweedfs** — S3 storage now that `minio/minio` is archived.
19. **Use The Index, Luke + dalibo/pev2 + explain.depesz.com** — indexing and plan reading, the two skills that fix most slow queries.
20. **pgbackrest/pgbackrest + benbjohnson/litestream** — PITR for Postgres and SQLite respectively.

Honourable mentions: ept/hermitage (isolation anomalies), zalando/restful-api-guidelines, standard-webhooks, pola-rs/polars + duckdb,
dlt-hub/dlt, debezium, meilisearch, pgvector, t3dotgg/stripe-recommendations, upstash/context7, anthropics/claude-plugins-official.

## 3. Agent-facing resources found (skills / MCP / plugins / llms.txt)

**MCP servers (database):** Postgres MCP Pro (restricted mode), DBHub (read-only, row limits), MCP Toolbox for Databases (tools.yaml,
16.7k★), MongoDB (official, readOnly), ClickHouse (official, read-only default), Redis (official, no server-side read-only → use ACL
user), MotherDuck/DuckDB, Qdrant (read-only flag), Elasticsearch, OpenSearch, Supabase (`read_only`, PAT), Neon (dev only), dbt MCP
(runs dbt CLI), AWS MCP monorepo (Aurora/DynamoDB/DocumentDB), Neo4j (official + Labs), mcp-alchemy (any SQLAlchemy DB, write-capable).
**MCP servers (framework/app):** Laravel Boost (official, also in claude-plugins-official), Tidewave for Phoenix and Rails (executes
code in the dev app), Rails MCP Server, Stripe AI (MCP + skills; money-moving), Context7 (docs), Cloudflare MCP, Resend MCP (sends mail),
Postman MCP, FastMCP `from_openapi()` to wrap any API.
**Skills:** supabase-postgres-best-practices, pg-aiguide (8 skills), prisma/skills, better-auth/skills (no LICENSE at root), Atlas
`skills/atlas` (runs shell), stripe/ai `skills/`, Oracle `oracle/skills` (Oracle DB only, UPL), webrpc (niche).
**Plugins / subagents / rule packs:** anthropics/claude-plugins-official (mcp-server-dev, security-guidance, LSP plugins for Go, Python,
Rust, Java, Kotlin, PHP, Ruby, C#, TS), wshobson/agents (backend-development, database-design, database-migrations, api-scaffolding,
data-engineering, payment-processing), VoltAgent subagents (api-designer, postgres-pro, sql-pro, graphql-architect, framework
specialists), github/awesome-copilot instructions (ASP.NET REST, Go, Rust, Spring Boot 4 migration, Quarkus, NestJS, Rails, Symfony,
SQL safety), PatrickJS/awesome-cursorrules (fastapi, go servemux, spring, laravel, phoenix, htmx; push slowing), Elixir `usage_rules`.
**llms.txt verified live (200):** hono.dev, orm.drizzle.team, prisma.io/docs, better-auth.com, docs.stripe.com, supabase.com,
elysiajs.com, zod.dev, pydantic.dev, docs.convex.dev, docs.nestjs.com, fastify.dev, duckdb.org, neon.com, docs.temporal.io, inngest.com,
trigger.dev, developers.cloudflare.com, clickhouse.com/docs, dagster.io/docs, getdbt.com, kysely.dev, phoenix.hexdocs.pm, ash.hexdocs.pm,
redis.io, mongodb.com/docs, qdrant.tech, meilisearch.com, typesense.org, docs.turso.tech, bun.sh, docs.deno.com, openfga.dev, ory.com,
polar.sh, upstash.com, docs.powersync.com, orpc.dev, trpc.io, docs.restate.dev, docs.hatchet.run, dbos.dev, windmill.dev, echo.labstack.com,
loco.rs, docs.nats.io, docs.redpanda.com, prefect.io, kestra.io, unkey.com, docs.svix.com, redocly.com, hurl.dev, openapis.org.
**No llms.txt (404):** fastapi.tiangolo.com, docs.litestar.dev, effect.website, pola.rs, laravel.com, postgresql.org, docs.bullmq.io,
zitadel, goauthentik.io, gin-gonic.com, docs.spring.io, debezium.io, ibis-project.org, standardwebhooks.com, connectrpc.com, buf.build.
Directories alive: llmstxt.site, directory.llmstxt.cloud, llmstxthub.com.
**Injection scan:** 10 fetched SKILL.md/README/CLAUDE.md files (supabase, better-auth, atlas, prisma, pg-aiguide, webrpc, oracle,
Mindrally, laravel/boost) contained no override/exfiltration instructions. Not every collection was scanned file-by-file; the
coordinator should re-scan anything before mirroring it as a skill.

## 4. Gaps I could not fill well

- No first-party llms.txt for FastAPI, Litestar, Laravel, Spring, Django, Go frameworks or postgresql.org — agents must rely on Context7 or mirrored docs.
- RFC 9457 problem-details libraries for Node and Python are tiny (<100★); a 50-line vendored handler is the honest answer.
- No dedicated, well-maintained idempotency-key middleware library worth listing; the topic is guides + Powertools' implementation.
- SQLite-specific agent skills do not exist yet (Postgres has two good packs); SQLite guidance is docs + Kerkour's checklist.
- MySQL-specific migration linting (beyond gh-ost/pt-osc/Skeema) and Oracle/SQL Server practice are thin — out of scope for a home server.
- JVM and .NET coverage is shallower than TS/Python/Go (frameworks, ORMs, jobs covered; fewer guides/skills found).
- PocketBase left GitHub (archived 2026-10-26, now self-hosted git at ganigeorgiev.com) so it cannot be verified with ghmeta; listed via its site.
- "Database branching" (Neon/Supabase branching, DBLab) is only mentioned in notes, not a topic.

## 5. Rejected items (and why)

Archived / moved: minio/minio (archived 2026-04, use Garage/SeaweedFS/RustFS/pgsty-silo) · localstack/localstack (OSS repo archived
2026-03, consolidated into commercial image) · varnishcache/varnish-cache (moved to vinyl-cache.org) · pocketbase GitHub repo (moved) ·
ts-rest/ts-rest · opticdev/optic (2026-01) · apiaryio/dredd (2024) · kuzudb/kuzu (2025-10 → LadybugDB) · encode/databases · google/wire ·
osohq/oso (legacy) · duo-labs/webauthn (Go) · pilcrowonpaper/oslo and /copenhagen (site kept as reference) ·
spring-attic/spring-authorization-server (merged into spring-security) · nucleuscloud/neosync (2025-08) · postgres-ai/postgres-checkup ·
supabase/supa_audit · node-fluent-ffmpeg · zombodb · modelcontextprotocol reference sqlite/postgres servers (servers-archived, 2025-05) ·
Azure/azure-mcp · PostHog/mcp · Replicache (archived; Zero is the successor).
Dead or dormant: soketi (2025-03, AGPL) · KeyDB (no release since 2023) · Stolon (2024-07) · sequinstream/sequin (maintenance mode) ·
djrobstep/migra (deprecated) · speakeasyjs/speakeasy · mailhog/MailHog · tulios/kafkajs (2024-08) · stepci (2024-08) · hydradatabase/columnar ·
shuttle-hq/synth · integresql (2024-01, mentioned only) · python-jose (slow) · Poem (last release 2022).
Licence: Liquibase (now FSL-1.1, not listed as install) · Inngest (SSPL server, GPL-3 SDK → reference only) · Directus (new "Monospace
Sustainable Core License", not listed) · CockroachDB (source-available since 2024 → reference) · Redis 8 (tri-licence → reference; Valkey
default) · Materialize (BSL + licence key, note only) · Hasura v3 DDN (cloud-only build service; v2 listed with EOL 2027-01) ·
weaviate/mcp-server-weaviate and ckanthony/openapi-mcp (no licence) · HenkDz/postgresql-mcp-server (AGPL, stale) · travisvn/awesome-claude-skills
(no licence) · a dozen <50★ unlicensed skill repos surfaced by code search (youlaitech, YepAPI, clawic, etc.).
Not found on GitHub today (dropped): paypal/api-standards, zenko/cloudserver, docxtemplater/docxtemplater, lemonsqueezy/lemonsqueezy.js,
jsx-email/jsx-email, bytebase/awesome-database-tools, depesz/explain.depesz.com (site used instead), tigerdata/pg-aiguide (real repo is
timescale/pg-aiguide), supabase-community/agent-skills (real repo is supabase/agent-skills).
Renames recorded in notes/URLs: prisma/prisma→prisma/orm · dbt-core→dbt-labs/dbt · TobikoData/sqlmesh→SQLMesh/sqlmesh · unnoq/orpc→middleapi/orpc ·
casbin/casbin→apache/casbin · hyperium/tonic→grpc/grpc-rust · launchbadge/sqlx→transact-rs/sqlx · jcrist/msgspec→msgspec/msgspec ·
fabian-hiller/valibot→open-circle/valibot · unjs/nitro→nitrojs/nitro · encode/starlette,uvicorn→Kludex/ · hey-api/openapi-ts→hey-api/hey-api ·
googleapis/genai-toolbox→googleapis/mcp-toolbox · supabase-community/supabase-mcp→supabase/mcp · stripe/agent-toolkit→stripe/ai ·
jlowin/fastmcp→PrefectHQ/fastmcp · snaplet/seed→supabase-community/seed · great_expectations→fivetran/ · wsvincent/djangox→lithium ·
gothinkster/realworld→realworld-apps/realworld · citusdata/pg_auto_failover→hapostgres/ · vitabaks/postgresql_cluster→autobase-tech/autobase.

## 6. Concerns

**Licences (biggest):** 2024–2026 saw an unusual number of infrastructure relicensings (Redis, Elasticsearch, MinIO archived, Liquibase,
Directus, CockroachDB, Zitadel→AGPL, Inngest SSPL, PowerSync/Convex FSL, Redpanda Connect mixed, Hanko/Permify/PgDog/Unleash/ParadeDB/Citus
AGPL). The catalog records each as found and marks AGPL/BSL/FSL/SSPL items `reference` or run-only; nothing non-permissive is marked
`vendor`. GitHub's licence detection is also wrong for ~40 listed repos (shows NOASSERTION/none for MIT/BSD/PostgreSQL-licensed
projects such as Bun, Rocket, htmx, TypeBox, Dapper, pgvector, Stalwart, Ash) — notes state the real licence; the coordinator should read
LICENSE files before mirroring anything flagged NOASSERTION/none.
**Safety of agent resources:** every DB MCP server needs credentials and most can write unless restricted; Tidewave and Laravel Boost
execute code inside the running app; Stripe MCP moves money; Resend MCP sends mail; Atlas skill runs the atlas CLI; Context7 and
pg-aiguide's MCP call remote services. Recommendation for the garage: ship DB MCPs with a read-only role template, mark these as
dev-only, and never auto-install skills without a LICENSE and a read of SKILL.md (better-auth/skills currently lacks a root LICENSE).
**Volatility / size:** several top picks are moving fast (RustFS, pgschema, PgDog, Turso DB, Drizzle v1 RC, Prisma 8 RC, Zero 1.0,
Postgres Language Server) — pin versions and re-run ghmeta quarterly; 8 repos were pushed again while this report was being written.
~620 repos includes huge monorepos (ClickHouse, Kafka, Flink, Spark, Superset, MongoDB, Elasticsearch, Neo4j, Keycloak); mirror only docs,
skills and `vendor`/`template` items, not full source, for anything marked `reference` or `install`.
**Scope overlaps for the coordinator:** `see_also` points to guessed ids in frontend (htmx, local-first, maps, uploads), security
(password cheat sheets, secrets, DB hardening, agent permissions), engineering (resilience, testing, reverse proxies, k8s operators,
observability, backups), systems (storage engines, media codecs), ai (RAG, MCP, skills authoring, notebooks) and mobile (push).
