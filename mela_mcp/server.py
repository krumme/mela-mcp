import base64
import json
from contextlib import closing
from pathlib import Path

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp_types import CallToolResult, Icon, TextContent

from . import appicon, db, imaging

MAX_IMAGES = 4

RECIPE_WIDGET_URI = "ui://mela/recipe.html"
_WIDGET_HTML = (Path(__file__).parent / "widgets" / "recipe.html").read_text(encoding="utf-8")

# The Apps extension: get_recipe binds to a Mela-styled UI resource so hosts
# that support MCP Apps (e.g. Claude Desktop) render the recipe + the user's
# real photos inline as a card. Populate it before constructing the server —
# MCPServer applies extensions in its constructor.
apps = Apps()
apps.add_html_resource(
    RECIPE_WIDGET_URI,
    _WIDGET_HTML,
    name="Mela recipe card",
    description="Renders a recipe and the user's photos as a Mela-styled card.",
)


@apps.tool(resource_uri=RECIPE_WIDGET_URI)
def get_recipe(recipe_id: int, ctx: Context | None = None) -> list:
    """Get one recipe's full detail (ingredients, instructions, notes, times, tags)
    by its numeric id from search_recipes.

    On hosts that support MCP Apps (e.g. Claude Desktop) a Mela-styled card with the
    user's real photos renders inline automatically. Present the recipe text; the
    photos appear only in that card and are not provided to you as content, so do
    not describe or substitute images. Never use stock or web photos."""
    recipe, payload = _load_recipe(recipe_id)
    if recipe is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"No recipe with id {recipe_id}.")],
            structured_content=payload,
        )

    # Model-facing `content` is the markdown (never base64). `structured_content`
    # still carries the widget payload for hosts that forward it on the push, but
    # Claude Desktop strips structuredContent from the tool-result it pushes to
    # the iframe — the widget's real data path is the app-only pull tool below.
    return CallToolResult(
        content=[TextContent(type="text", text=_format_recipe_markdown(recipe))],
        structured_content=payload,
    )


@apps.tool(resource_uri=RECIPE_WIDGET_URI, visibility=["app"])
def get_recipe_widget_data(recipe_id: int, ctx: Context | None = None) -> list:
    """App-only data feed for the Mela recipe card. The widget iframe calls this
    itself (Krea's get_job pattern) via a host-relayed tools/call after Claude
    Desktop strips structuredContent from the pushed tool-result. Never surfaced
    to the model, so the base64 photo data URIs stay out of model context."""
    _, payload = _load_recipe(recipe_id)
    # The payload rides BOTH channels: structuredContent for spec-faithful hosts,
    # and a compact JSON text block the widget parses when the host strips
    # structuredContent from responses too (Krea's recovery path). Safe here
    # only because visibility=["app"] keeps this content off the model path.
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))],
        structured_content=payload,
    )


def _load_recipe(recipe_id: int) -> tuple[dict | None, dict]:
    """Load one recipe and its widget payload: (recipe row | None, payload)."""
    with closing(db.connect()) as conn:
        recipe = db.get_recipe(conn, recipe_id)
        if recipe is None:
            return None, {"not_found": True, "recipe_id": recipe_id}

        count = min(recipe.get("image_count", 0), MAX_IMAGES)
        db_path = db.get_db_path()
        image_uris: list[str] = []
        for index in range(count):
            raw = db.get_recipe_image_bytes(conn, db_path, recipe_id, index)
            if raw is None:
                continue
            jpeg = imaging.to_jpeg(raw)
            if jpeg is None:
                continue
            image_uris.append("data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"))

        return recipe, _widget_payload(recipe, image_uris)


def _widget_payload(recipe: dict, image_uris: list[str]) -> dict:
    """The JSON payload delivered to the widget (camelCase for the JS side)."""
    return {
        "title": recipe.get("title"),
        "link": recipe.get("link"),
        "tags": recipe.get("tags") or [],
        "yield": recipe.get("yield"),
        "prepTime": recipe.get("prep_time"),
        "cookTime": recipe.get("cook_time"),
        "totalTime": recipe.get("total_time"),
        "description": recipe.get("description"),
        "ingredients": recipe.get("ingredients"),
        "instructions": recipe.get("instructions"),
        "notes": recipe.get("notes"),
        "nutrition": recipe.get("nutrition"),
        "images": image_uris,
    }


def _format_recipe_markdown(recipe: dict) -> str:
    lines = [f"# {recipe['title']}"]

    times = []
    if recipe.get("prep_time"):
        times.append(f"Prep: {recipe['prep_time']}")
    if recipe.get("cook_time"):
        times.append(f"Cook: {recipe['cook_time']}")
    if recipe.get("total_time"):
        times.append(f"Total: {recipe['total_time']}")
    if times:
        lines.append(" | ".join(times))

    if recipe.get("yield"):
        lines.append(f"**Yield:** {recipe['yield']}")

    if recipe.get("tags"):
        lines.append(f"**Tags:** {', '.join(recipe['tags'])}")

    if recipe.get("link"):
        lines.append(f"**Source:** {recipe['link']}")

    if recipe.get("ingredients"):
        lines.append("\n## Ingredients")
        lines.append(recipe["ingredients"])

    if recipe.get("instructions"):
        lines.append("\n## Instructions")
        lines.append(recipe["instructions"])

    if recipe.get("notes"):
        lines.append("\n## Notes")
        lines.append(recipe["notes"])

    return "\n".join(lines)


_icon_uri = appicon.mela_icon_data_uri()
if _icon_uri:
    mcp = MCPServer(
        "mela",
        icons=[Icon(src=_icon_uri, mime_type="image/png", sizes=["128x128"])],
        extensions=[apps],
    )
else:
    mcp = MCPServer("mela", extensions=[apps])


@mcp.tool()
def search_recipes(query: str, tag: str | None = None,
                   favorite: bool | None = None,
                   want_to_cook: bool | None = None, limit: int = 20) -> list[dict]:
    """Full-text search the Mela recipe library. All words must match.
    Optional filters: tag name, favorite, want_to_cook. Returns id/title/tags/snippet
    (text only, no photos). Call get_recipe with a result's id to show the full
    recipe together with the user's real photos."""
    with closing(db.connect()) as conn:
        return db.search_recipes(conn, query, tag=tag, favorite=favorite,
                                 want_to_cook=want_to_cook, limit=limit)


@mcp.tool()
def list_tags() -> list[dict]:
    """List all recipe tags/categories with how many recipes carry each."""
    with closing(db.connect()) as conn:
        return db.list_tags(conn)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
