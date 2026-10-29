# Using the garage on the home server

Every Claude Code session on the server already has the garage: users `lechuuu`, `claude`
(the assistant) and `user`, in any folder, with nothing to set up per project.

This page describes the owner's own server, where the garage was built. Anyone else: [use-anywhere.md](use-anywhere.md).

## For you (the owner)

1. Open Claude Code anywhere on the server (`claude`).
   Why: the garage plugin comes with every session, so there is nothing to install.
2. Ask for what you need in plain words, for example "I need a headless dialog in React".
   Why: the plugin's `find` skill tells Claude to search the garage before it builds anything.
3. If you want to see it is there, type `/plugin` and look for **garage** (from **code-garage**).
   Why: it confirms the plugin loaded; it lists 3 skills (find, use, propose), 1 agent (librarian) and the MCP server.
4. Claude says "reviewed, not yet trusted" when it uses an item you haven't approved yet. That is expected.
   Why: only your weekly tap makes an item `trusted`; until then it may be used only while you are watching.

## What a session can do

| Command (Bash) | MCP tool | What |
|---|---|---|
| `garage search "need" --json` | `search` | topics with their best resource: licence, trust, install line, local copy |
| `garage show ID` | `show` | one topic or resource in full (the tier is printed first) |
| `garage grep ID PATTERN` | `grep` | regex inside one item's local snapshot |
| — | `recipe` | the exact steps to add or install one item, its licence duty, and whether trust allows it here |
| `garage add ID --into vendor/` · `garage skill add ID` · `garage new NAME --template ID` | — | copy in, with LICENSE and `.garage.json` |
| `garage propose URL --topic ID --why "…"` | — | suggest an addition (a pull request) |

Trust in one breath: `quarantine` = read only; `reviewed` = fine in interactive sessions (say so); `trusted` = fine
unattended; with `GARAGE_UNATTENDED=1` (scheduled jobs) only `trusted` items. 9 items are `trusted` (approved 2026-10-29) and
6 more are `reviewed`. `garage add` and `garage skill add` copy from the server's local mirror (or from GitHub at the pinned commit if the
mirror lacks the path) and refuse a `quarantine` item. Run them in a project folder, never inside `/data/apps/garage`.

The assistant (user `claude`) can use the `garage` command. The MCP tools (`mcp__plugin_garage_garage__*`) are
read-only, but its `dontAsk` permission list doesn't include them yet: add `mcp__plugin_garage_garage` to its allow
list if you want it to use them (owner decision). `lechu-job` runs use `--strict-mcp-config`, so they get the
command only.

## How it is wired (for the admin)

- **Warning:** never run `claude -p` (or any `claude` session) as user `claude` without `--strict-mcp-config` (add
  `--mcp-config` for the garage MCP if you need it): it loads the assistant's channel plugin, and a second poller
  knocks the assistant's bot offline until the assistant is restarted. The watchdog restarts the assistant once if
  its channel plugin is gone, and alerts if that does not help.
- The assistant may read `/data/apps/garage/quarantine` and nothing more: its safety hook refuses to run, copy or
  write anything there, and allows only `garage show`, `grep`, `search` and `scan` on it.

- Code and catalog: `/data/apps/garage/repo` (user `garage`), the Python environment `/opt/garage/venv` (exact pins),
  the commands `/usr/local/bin/garage` and `garage-mcp`.
- Registration: `/etc/claude-code/managed-settings.d/50-garage.json` adds the marketplace `code-garage` (a `directory`
  source read in place, no copy) and force-enables `garage@code-garage`. `managed-settings.json` (the channels switch
  and the safety hook) is not touched. Claude Code registers the marketplace itself for each user at their next session.
- Install or update: `sudo ~/lechu-build/bootstrap/96-garage.sh install` (pulls the repo, reruns every
  `infra/install.d/` step). During the build: `sudo ~/code-garage/infra/install.sh --src ~/code-garage`.
- Check: `sudo ~/lechu-build/bootstrap/96-garage-check.sh` (it also proves the plugin loads for `lechuuu` and `claude`,
  without a model call).
- Turn the plugin off for everyone: `sudo /data/apps/garage/repo/infra/install.d/40-access.sh remove`.
- The tailnet MCP for the Mac is the `garage` stack: see `use-on-mac.md`.
