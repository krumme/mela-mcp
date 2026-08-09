# mela-mcp

An unofficial, read-only MCP server that exposes recipes from the Mela macOS app
(`search_recipes`, `get_recipe`, `list_tags`) to MCP-compatible assistants.

## Conventions

- All SQL and schema knowledge lives in `mela_mcp/db.py`; `mela_mcp/server.py` only
  wraps those helpers as MCP tools — don't put SQL in server.py.
- Read-only forever — never add write queries against Curcuma.sqlite; future writes
  must go through Mela's own import surface (`mela://` URLs, `.melarecipe` files, or
  Shortcuts/App Intents), never direct DB writes (it's a CloudKit-synced Core Data
  store).
- Requires `mcp>=2.0` (`MCPServer`); the older `FastMCP` API is gone.
- Run tests with `python -m pytest`. The live test (`tests/test_live.py`) needs Mela
  installed and skips otherwise.
