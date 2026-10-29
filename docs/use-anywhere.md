# Using the garage anywhere

Nothing here talks to the owner's
server: everything runs on your own machine over the public catalog.

## With Claude Code (the plugin)

1. Install uv: see https://docs.astral.sh/uv/ (`brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`).
   Why: the plugin's `garage` command and MCP server run through `uvx`; no other setup.
2. `claude plugin marketplace add agent-lechuuu/code-garage`
   Why: registers the garage's marketplace (a public GitHub repo, no login needed).
3. `claude plugin install garage@code-garage`
   Why: installs the skills (find, use, propose), the librarian agent, the `garage` command and the local MCP server.
4. Start `claude` and ask for what you need ("a rate limiter in Go").
   Why: the `find` skill makes Claude search the garage before it writes code from scratch.

Pin a release instead of following the default branch: `claude plugin marketplace add agent-lechuuu/code-garage@<tag>`.

## Without the plugin

- The command line: `uvx --from git+https://github.com/agent-lechuuu/code-garage garage search "headless dialog react"`.
- The MCP server for any MCP client (stdio): command `uvx`, arguments
  `--from git+https://github.com/agent-lechuuu/code-garage garage-mcp`. For Claude Code without the plugin:
  `claude mcp add garage -- uvx --from git+https://github.com/agent-lechuuu/code-garage garage-mcp`.
- The catalog as data: `dist/catalog.json` and `INDEX.md` in the repo.

## What you get, and the rules

- `garage add` fetches the pinned commit of an item from GitHub, keeps its LICENSE and NOTICE and writes a
  `.garage.json` record. On the owner's server it copies from the local mirror instead.
- Items without an upstream licence cannot be added (link only). Licences stay with each item: see the `license`
  field in `garage show`.
- Trust tiers: `quarantine` (read only), `reviewed` (interactive use; say so), `trusted` (fine unattended;
  `GARAGE_UNATTENDED=1` allows only these). The trust records ship in the repo, so what the owner reviewed shows as
  `reviewed` for everyone. Most of the catalog is still `quarantine`, which `add` refuses.
- `garage grep` needs a local snapshot; off the server there is none ("not mirrored here").
- There is no hosted garage MCP for the public; the server behind the owner's MCP is private.
