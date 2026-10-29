# S1 `frontend` — research report (2026-10-28)

Catalog: `frontend.yaml` — **150 topics, 717 resources** (619 GitHub resources across 589 unique repos, 98 non-GitHub:
docs, llms.txt files, tools, courses, CodePen profiles). 49 resources are agent-facing (18 skills, 29 MCP servers,
2 plugins). 20 topics carry sourced `practices`.

Method: candidate lists from awesome lists (awesome-shadcn-ui, awesome-tailwindcss, awesome-react-native,
awesome-flutter, awesome-electron, awesome-design-systems), official "ecosystem" pages and the shadcn registry
directory; **every GitHub repo verified live with ghmeta.py** (8 batches, ~620 repos; stars/pushed/archived in the
YAML are copied programmatically from those results, never typed by hand). ~115 repos that GitHub reported as
`NOASSERTION`/`none` had their LICENSE text or package.json read individually. 384 non-GitHub URLs were probed with
curl (status codes), and every `llms.txt` returning 200 was checked for real text vs. SPA fallback. SKILL.md/README of
every listed skill and MCP server was read for content and prompt-injection; none contained instructions aimed at
agents beyond their stated purpose.

## Map of the slice (area → topics)

| area | topics | covers |
|---|---|---|
| frameworks | 9 | React/Next, Vue/Nuxt, Svelte, Solid/Qwik/Preact, Astro, Angular, htmx/Alpine, Web Components, docs generators |
| build | 4 | Vite/Rolldown, other bundlers + Turborepo, lint/format (Biome), bundle analysis |
| styling | 9 | Tailwind v4 + utilities, zero-runtime CSS, PostCSS/Lightning, modern CSS features, layout, tokens, classic frameworks, practices/resets |
| components | 15 | shadcn/ui, registries, ports, headless (React / cross-framework), styled libs, Vue/Svelte libs, Tailwind kits, animated kits (Magic UI/React Bits/Aceternity), micro-interaction kits, shadcn extensions, landing blocks, toasts/cmdk, CJK enterprise libs |
| design | 11 | design systems (incl. GOV.UK/USWDS), inspiration galleries, craft/micro-interactions, UX principles, colour, fonts, type scales/loading, icon sets, icon/SVG tooling, illustrations/backgrounds, CSS generators |
| animation | 9 | Motion, GSAP/Lenis, CSS animation libs, View Transitions, scroll-driven, Lottie/Rive, carousels, text/particles/confetti, loaders |
| 3d | 6 | three.js + globes, R3F, Threlte/Tres/Babylon, shaders + GPU fundamentals, 2D canvas engines, generative tools |
| dataviz | 7 | React charts, agnostic charts, D3/grammars, diagrams/flows, graphs, chart design practices, whiteboards |
| forms | 7 | React forms (+JSON Schema), schema validation, Vue/Svelte/server actions, masks/phone/OTP, dates/pickers, upload/crop, selects/pickers |
| state | 5 | client + URL state, server state, API clients/OpenAPI codegen, hooks collections, local-first storage |
| data-display | 4 | tables, virtualization, spreadsheets/pivots, panels/docking/grids/trees |
| editors | 5 | rich text, block editors, code editors, Markdown/highlighting, PDF + math |
| interaction | 2 | drag and drop, gestures/transforms |
| maps | 2 | web maps, geo dataviz |
| a11y | 3 | standards/patterns, testing tools, focus/dialogs |
| perf | 6 | Core Web Vitals, audit automation, images, loading strategies, React perf, browser-support data |
| i18n | 2 | libraries, tooling/RTL |
| pwa | 2 | service workers, assets/manifest/push |
| seo | 2 | head/metadata/OG, structured data/sitemaps |
| email | 2 | component frameworks, templates/compatibility |
| templates | 5 | shadcn dashboards, admin frameworks, SaaS starters, Next boilerplates/examples, landing pages |
| mobile | 13 | RN/Expo, RN UI+styling, animation/gestures, navigation/lists, native modules, starters/reference apps, testing/devtools, RN agent resources, Flutter (+Dart MCP), Flutter state, Flutter UI kits, hybrid/emerging, native iOS/Android/KMP |
| desktop | 3 | Tauri, Electron (+boilerplates), alternatives (Wails, Electrobun, iced, egui) |
| testing | 4 | Storybook (+MCP addon), component/unit + MSW/Faker, visual regression, Playwright for UI |
| agent | 10 | design skills, React skills + Next MCP, visual/video skills, registry MCPs, design-tool MCPs, framework MCPs, browser/DevTools MCPs, llms.txt docs, rules/subagent collections, skills ecosystem |
| codepen | 3 | creators, roundups/challenges, CSS-only technique sources |

## The 20 most valuable resources and why

1. **shadcn-ui/ui** (MIT, 127k) — the component vocabulary everything else in the React world now targets; the official
   **shadcn MCP** (`npx shadcn@latest mcp init --client claude`) lets an agent browse and install from any registry.
2. **anthropics/skills → skills/frontend-design** (Apache-2.0) — the first-party design-direction skill; the base that
   Impeccable and others build on. Pure instructions, no code execution.
3. **pbakaus/impeccable** (Apache-2.0, 92k) — design vocabulary + 24 commands + 62 deterministic "AI slop" detector
   rules runnable without an LLM. Best single upgrade for UI quality.
4. **nextlevelbuilder/ui-ux-pro-max-skill** (MIT, 142k) — 192 reasoning rules and 79 searchable UI styles with
   palettes/fonts per product type; uses a local Python CLI for search.
5. **vercel-labs/agent-skills** (MIT per skill) — react-best-practices (70 prioritised perf rules),
   web-design-guidelines (audits code against vercel-labs/web-interface-guidelines), composition-patterns,
   react-view-transitions, react-native-skills.
6. **ibelick/ui-skills** (MIT) — baseline-ui "deslop" pass, improve-ui audit, fixing-accessibility,
   fixing-motion-performance, create-design-md; also an MCP at ui-skills.com/mcp.
7. **ChromeDevTools/chrome-devtools-mcp** (Apache-2.0, 54k) — official DevTools MCP: perf traces, network, console,
   screenshots; the way an agent verifies what it built.
8. **Figma remote MCP** (`https://mcp.figma.com/mcp`, OAuth) + **GLips/Figma-Context-MCP** (MIT) — design-to-code.
9. **motiondivision/motion** (MIT) + motion.dev/llms.txt (65 KB) — the animation library and the most complete
   agent-readable animation docs.
10. **mui/base-ui**, **radix-ui/primitives**, **adobe/react-spectrum** (React Aria) — the three accessible headless
    foundations; Base UI 1.0 is the newest and shadcn now offers Base UI variants.
11. **magicuidesign/magicui** (MIT) and **DavidHDev/react-bits** (MIT + Commons Clause, 50k) — the animated-component
    kits that make landing pages look expensive; licence difference matters (see concerns).
12. **cosscom/ui** (Origin UI → coss.com/ui, MIT, 500+ components) — the largest permissive shadcn extension set.
13. **TanStack** (query/table/virtual/form/router/db, MIT) + tanstack.com/llms.txt — the data layer for any framework.
14. **react-hook-form + colinhacks/zod** (MIT) — forms + validation default; zod.dev/llms.txt.
15. **expo/expo + expo/skills + Expo MCP** (`https://mcp.expo.dev/mcp`) — the complete official mobile agent stack.
16. **tauri-apps/tauri** (Apache-2.0, 112k) with v2.tauri.app/llms.txt — default desktop/mobile shell.
17. **storybookjs/storybook** with `@storybook/addon-mcp` (code/addons/mcp) — component docs, stories and tests
    exposed to agents at `localhost:6006/mcp`.
18. **dequelabs/axe-core(+npm)** (MPL-2.0) + w3c/aria-practices + WCAG 2.2 quickref — the a11y verification stack.
19. **GoogleChrome/web-vitals + lighthouse-ci + harlan-zw/unlighthouse** — field and lab performance measurement.
20. **Codrops GitHub org** (100+ MIT demo repos, pushed weekly) + **Temani Afif's sites** (css-loaders.com,
    css-shape.com, css-generators.com, css-pattern.com) — the copyable version of "the best of CodePen".

## Notable agent skills, MCP servers and plugins

Skills: anthropics/skills (frontend-design, web-artifacts-builder, theme-factory, canvas-design, algorithmic-art,
brand-guidelines, webapp-testing), pbakaus/impeccable, nextlevelbuilder/ui-ux-pro-max-skill, ibelick/ui-skills,
vercel-labs/agent-skills (5 frontend skills), expo/skills (official), remotion-dev/skills (official),
dart-lang/ai `skills` CLI (skills shipped inside Dart packages), daisyui.com/llms.txt (served as a SKILL.md).

MCP servers (official): shadcn (`shadcn@latest mcp`), Figma remote, Expo remote, Svelte (`@sveltejs/mcp` /
mcp.svelte.dev — repo renamed to sveltejs/ai-tools), Angular (`ng mcp`), Vuetify (vuetifyjs/mcp), Nuxt/Vite
(antfu/nuxt-mcp-dev), Next.js (vercel/next-devtools-mcp proxies `/_next/mcp`), Storybook addon-mcp, Chrome DevTools,
Playwright MCP, Dart (dart_mcp_server), Framer MCP. Community: Jpisnice/shadcn-ui-mcp-server, magicuidesign/mcp,
Cult UI MCP, 21st MCP (hosted, API key), GLips/Figma-Context-MCP, davideast/stitch-mcp, upstash/context7.

Plugins/collections: wshobson/agents (ui-design, frontend-mobile-development, accessibility-compliance,
brand-landingpage), VoltAgent/awesome-claude-code-subagents, PatrickJS/awesome-cursorrules, cursor/community-plugins.

Verified llms.txt (real text, 2026-10-28): shadcn, Mantine, Base UI, Ark, Chakra, Panda, Reka, Nuxt UI, Vuetify,
HeroUI, daisyUI, Lucide, Magic UI, React Bits, Cult UI, Animate UI, Intent UI, Untitled UI, React Aria, Aceternity,
Next.js, Nuxt, Svelte, React, Vue, Angular, React Native, Expo, Motion, GSAP, TanStack, Zod, Vite, Tauri, Storybook,
Tiptap, UnoCSS, three.js (stub), R3F. **404**: Tailwind, Astro, Lit, htmx, Qwik, Biome, D3, ECharts, Flutter,
Electron, Radix, react-email. SolidJS and Origin UI serve HTML at /llms.txt (not usable).

## Renames and moves found (training knowledge was wrong)

facebook/react → react/react; facebook/react-native → react/react-native; 11ty/eleventy → 11ty/buildawesome;
cschroeter/park-ui → chakra-ui/park-ui; origin-space/originui → cosscom/ui; haydenbleasel/kibo → shadcnblocks/kibo;
pacocoursey/cmdk → dip/cmdk; fabian-hiller/valibot → open-circle/valibot; quilljs/quill → slab/quill;
Shopify/react-native-skia → wcandillon/react-native-skia; mrousavy/{mmkv,vision-camera,nitro} → margelo/*;
sveltejs/mcp → sveltejs/ai-tools; antfu/nuxt-mcp → antfu/nuxt-mcp-dev; pontusab/directories →
cursor/community-plugins; 21st-dev/magic-mcp is now a proxy to the hosted 21st MCP; shoelace → Web Awesome;
**CodeMirror and ProseMirror left GitHub** (all repos archived 2026-04; development at code.haverbeke.berlin, a
Forgejo instance) — listed as docs-site resources with that note.

## Gaps not filled

- **CodePen itself is unverifiable**: codepen.io returns 403 to curl and WebFetch. The 5 creator profiles listed are
  from public references, not live checks; no collection URLs are listed because none could be confirmed. The
  substitute is copyable sources (Codrops repos, Temani Afif's sites, Uiverse, Alvaro Montoro's monthly roundups).
- No official MCP found for HeroUI, Chakra, Mantine, Ant Design (only third-party, low-star servers; omitted).
- Google Stitch has no first-party MCP; listed the Gemini CLI extension and davideast/stitch-mcp (Apache-2.0).
- Design-to-code SaaS (Builder.io Fusion, Locofy, Anima, v0) are paid/closed; only Figma MCP + Framelink are listed.
- Tailark and Aceternity UI distribute via registries/sites only (no repo); listed as `snippet` with site-stated licence.
- Could not read the SKILL.md of ui-ux-pro-max (path is a directory tree); judged from README + CLI structure.

## Rejected items (and why)

- **lost-pixel/lost-pixel, storybookjs/test-runner, storybookjs/mcp, penpot/penpot-mcp, GoogleChromeLabs/critters,
  shoelace-style/shoelace, Shopify/polaris-react-archive, codemirror/dev, ProseMirror/prosemirror, nhn/tui.editor,
  joe-bell/plaiceholder, expo/router, vercel/commerce, webfansplz/vite-plugin-vue-devtools** — archived (successors
  listed where they exist: Vitest addon, addon-mcp, Web Awesome, beasties, expo/expo).
- **x1xhlol/system-prompts-and-models-of-ai-tools** (v0/Cursor leaked prompts) — GPL-3.0 and leaked proprietary
  material; not something the garage should mirror.
- **mattboldt/typed.js** — relicensed GPL-3.0 (2026); mentioned as reference only. **tengbao/vanta** — unmaintained.
- **Hover.css** (MIT personal / paid commercial), **Handsontable** (non-commercial only), **ApexCharts** (now dual
  licence), **tldraw** (watermark licence), **Remotion** (company licence above 3 people), **GSAP** (free but not
  OSI) — listed only where the tool is irreplaceable, with the licence stated and `use: reference/install` not `vendor`.
- **thebookofshaders repo** (all rights reserved), **lygia** (Prosperity, non-commercial) — reference only.
- **react-leaflet** and **animate.css** — Hippocratic-2.1 (ethical-use clause, not OSI); listed with a practice note
  steering to MapLibre/react-map-gl and transition.css.
- **hesreallyhim/awesome-claude-code** — CC-BY-NC-ND; read, do not redistribute. **nilbuild/developer-roadmap** —
  personal-use licence; omitted.
- Low-signal MCPs (T-hash06/heroui-mcp 17 stars, Microck/registry-directory-mcp 0 stars, rudra016/aceternityui-mcp
  25 stars) and 21st.dev's repo (last push 2025-05) — not listed or listed as tier 3 with caveats.
- Stale classics kept deliberately (noted in `note`): SpinKit, rough-notation, flatpickr, clsx, use-gesture, AOS,
  imaskjs, postmark/mailgun templates, Cerberus. Nothing pushed before 2022 is listed except finished snippet sets.

## Concerns

1. **Commons Clause creep in UI kits**: React Bits (50k) and Animate UI are "MIT + Commons Clause" (use in apps OK,
   reselling as a library forbidden). Fine for the owner's projects, but the garage must not re-publish them as a
   component library. Preline is dual MIT/Fair-Use. All flagged in `license`.
2. **Skills and MCPs that execute code or need network/credentials**: web-artifacts-builder (shell + npm install),
   webapp-testing and canvas-design (Python), ui-ux-pro-max (Python CLI), impeccable (npx CLI/browser extension),
   web-design-guidelines (fetches rules from GitHub at run time), Figma/Expo/Framer/21st/Context7 (remote services,
   OAuth or API keys), Chrome DevTools and Playwright MCPs (control a browser that can reach any URL). All marked in
   `note`. No prompt-injection content was found in any read file.
3. **Size and churn**: anthropics/skills, obra/superpowers and the plugin marketplaces are large and fast-moving; mirror
   only the frontend skill folders (paths given). The shadcn registry directory warns to review third-party registry
   code before installing; the garage should pin registry item versions rather than fetch `@latest` at build time.
4. **CodePen content cannot be mirrored legally or technically** (no licence per pen, bot-blocked); the catalog points
   at MIT/CC0 equivalents instead.
5. **GitHub licence detection is unreliable**: ~115 of ~620 repos needed manual reading (monorepos, custom licences).
   The `license` field is as found; "none" means no licence file (89 resources, mostly lists/sites) — treat as
   reference-only.
