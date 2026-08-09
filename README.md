# mela-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that lets an MCP-compatible
assistant (Claude Code, Claude Desktop, etc.) search and read recipes stored by the
[Mela](https://mela.recipes) macOS app.

**Unofficial, third-party project. Not affiliated with, endorsed by, or supported by
Mela or Mela's developers.** It reads Mela's local database directly; it does not use any
official Mela API.

## Requirements

- macOS, with the Mela app installed and at least one recipe saved locally.
- Python 3.10+.

## What it does

Three model-facing tools, all read-only:

- **`search_recipes`** — full-text search across title, ingredients, instructions,
  notes, description, nutrition, and link. All words in the query must match.
  Optional filters: `tag`, `favorite`, `want_to_cook`. Text only, no photos.
- **`get_recipe`** — full detail for one recipe, by the numeric id returned from
  `search_recipes` (ingredients, instructions, notes, times, tags). On hosts that
  support MCP Apps (Claude Desktop), it also renders a **Mela-styled card with your
  real photos inline** — your own photos, downscaled, never stock images. The
  photos display in that card; they are not sent to the model as text.
- **`list_tags`** — every tag/category in your library with its recipe count.

That's it — no writing, no shopping lists, no meal planning. The server opens Mela's
SQLite database read-only and never modifies it.

Example things you could ask an assistant connected to this server:

- "What can I make with chicken and kale?"
- "Show me my prime rib recipe."
- "What tags do I have, and which one has the most recipes?"

## Install

Install it from a local checkout of the source:

```bash
git clone https://github.com/krumme/mela-mcp.git
cd mela-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then register it with your MCP host, pointing at the venv's Python you just created.

**Claude Code:**

```bash
claude mcp add mela -- /absolute/path/to/mela-mcp/.venv/bin/python -m mela_mcp.server
```

Substitute the actual path to the venv you created above.

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mela": {
      "command": "/absolute/path/to/mela-mcp/.venv/bin/python",
      "args": ["-m", "mela_mcp.server"]
    }
  }
}
```

## Configuration

- **`MELA_DB_PATH`** (optional) — overrides the path to Mela's database. Leave it
  unset (or blank) to auto-detect the default location:
  `~/Library/Group Containers/66JC38RDUD.recipes.mela/Data/Curcuma.sqlite`

## Caveats

- macOS only — Mela's database lives in a macOS app container.
- **macOS privacy prompt.** macOS shows a dialog like *"python… would like to access
  data from other apps."* the first time (and, for an unsigned Python interpreter,
  often on *every* launch) the server reads Mela's app container. Clicking **Allow**
  works but usually won't persist for a bare interpreter. The durable fix is to grant
  **Full Disk Access** to your MCP host: **System Settings → Privacy & Security →
  Full Disk Access**, then add the **Claude** app (for Claude Desktop) or your
  **terminal** app (for Claude Code) — its child Python process inherits the access.
  The access is read-only, to your own recipes.
- If the server still can't find your database, set `MELA_DB_PATH` explicitly.
- Read-only by design: the server only ever opens the database in read-only mode
  and never writes to it.
- Photos render only in the inline card on hosts that support MCP Apps (Claude
  Desktop). On other clients you get the recipe text; the model isn't handed the
  photos, so it can't display them itself. Whether the card renders is up to the
  host — this server can't force it.

## Development / tests

```bash
python -m pytest
```

The live tests (`tests/test_live.py`) read your real Mela library, so they are
**opt-in** — otherwise they'd trigger a macOS privacy prompt on every run. Enable
them explicitly:

```bash
MELA_LIVE_TEST=1 python -m pytest
```

Plain `python -m pytest` skips them (and they also skip when Mela isn't installed).
