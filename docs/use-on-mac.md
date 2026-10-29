# Using the garage on your Mac

Two parts. Part 1, the **plugin** (skills, the librarian, a search over the catalog), works alone. Part 2, the
**server's MCP** over Tailscale, adds the server's index and its offline copies of the repos. About 15 minutes.

## Part 1: the plugin

1. Install uv: `brew install uv`.
   Why: on the Mac the plugin's `garage` command runs through `uvx` (nothing is installed on the Mac besides this).
2. Add the garage's marketplace: `claude plugin marketplace add agent-lechuuu/code-garage`.
   Why: it tells Claude Code where the garage plugin lives.
3. Install the plugin: `claude plugin install garage@code-garage`.
   Why: this copies the plugin into Claude Code; new sessions load it.
4. Check: start `claude`, type `/plugin`, and look for **garage** (3 skills: find, use, propose; the agent librarian).
   Why: it confirms the plugin loaded. The first search takes longer: `uvx` downloads the garage once.
5. Later, to get the newest catalog: `claude plugin marketplace update code-garage`, then
   `claude plugin update garage@code-garage`, then restart Claude Code.
   Why: the Mac keeps the version it installed until you ask for an update.

On the Mac the plugin has its own copy of the catalog and no offline snapshots, so `garage grep` says "not mirrored
here". `garage add` fetches the pinned commit from GitHub. Part 2 gives you the server's side.

## Part 2: the server's MCP over Tailscale (optional)

You need Tailscale on and the Mac logged in to your tailnet. Nothing on the server opens to the internet.

1. Add the server's garage to Claude Code, with its key fetched from the server, in one line:

   ```
   claude mcp add --transport http garage https://garage.<your-tailnet>.ts.net/mcp --scope user -H "Authorization: Bearer $(ssh <server> sudo lechu-secret show garage MCP_TOKEN)"
   ```

   Why: the key proves to the server that the call comes from you. It travels over `ssh <server>` and is never printed.
   `--scope user` makes it work in every folder.
2. Check: `claude mcp list` shows `garage ... ✓ Connected`.
   Why: it proves the Mac reaches the server's garage through Tailscale.
3. Use it: in Claude Code ask "search the garage for a headless dialog in React".
   Why: Claude calls the server's `search`, `show`, `grep` and `recipe` tools. They only read.

If both parts are on, Claude has two garages (the plugin's local one and the server's). That is fine; the server's one
sees the offline copies.

If the key ever leaks: rotate it on the server (see the server's own notes), then on the Mac `claude mcp remove garage -s user`
and step 1 again.
