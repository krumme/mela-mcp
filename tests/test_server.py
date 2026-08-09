import asyncio
import json
import shutil

import pytest
from mcp_types import CallToolResult, TextContent

from mela_mcp import server

sips_missing = shutil.which("sips") is None

def test_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"search_recipes", "get_recipe", "list_tags", "get_recipe_widget_data"}

def test_search_tool_returns_results(mela_db):
    hits = server.search_recipes("chicken")
    assert hits[0]["title"] == "Lemon Chicken"

def test_get_recipe_tool_unknown_id(mela_db):
    out = server.get_recipe(999)
    assert isinstance(out, CallToolResult)
    assert out.structured_content == {"not_found": True, "recipe_id": 999}
    assert "No recipe with id 999." in out.content[0].text

def test_list_tags_tool(mela_db):
    tags = {t["tag"] for t in server.list_tags()}
    assert "Dinner" in tags

@pytest.mark.skipif(sips_missing, reason="sips not available on this platform")
def test_get_recipe_returns_text_and_image_uris(mela_db):
    out = server.get_recipe(1)
    assert isinstance(out, CallToolResult)
    assert "Lemon Chicken" in out.content[0].text
    images = out.structured_content["images"]
    assert len(images) == 1
    assert images[0].startswith("data:image/jpeg;base64,")
    # No base64 leaks into model-facing text.
    assert "base64" not in out.content[0].text

def test_get_recipe_no_image(mela_db):
    out = server.get_recipe(3)
    assert isinstance(out, CallToolResult)
    assert "Chocolate Cake" in out.content[0].text
    assert out.structured_content["images"] == []


# ---- MCP Apps widget wiring ----

def test_recipe_widget_resource_registered():
    resources = asyncio.run(server.mcp.list_resources())
    uris = {str(r.uri) for r in resources}
    assert server.RECIPE_WIDGET_URI in uris

def test_recipe_widget_html_present_and_self_contained():
    html = server._WIDGET_HTML
    assert html.strip()
    assert "ui/initialize" in html
    assert "ui/notifications/tool-result" in html
    # No external network references in the static widget.
    assert "http://" not in html
    assert "https://" not in html
    assert "<script src" not in html
    assert "<link " not in html

def test_recipe_widget_tolerant_data_plumbing():
    # Pins the Krea-matching host contract: tolerant tool-result envelope
    # (params.result / params.toolResult / params / message.result), a JSON
    # text-content fallback beside structuredContent, and an initialized
    # handshake that fires even when the host never answers ui/initialize.
    html = server._WIDGET_HTML
    assert "params.result" in html
    assert "params.toolResult" in html
    assert "message.result" in html
    assert "structuredContent" in html
    assert "JSON.parse" in html
    assert "sendInitialized" in html
    assert "window.setTimeout(sendInitialized" in html
    # The strict source gate that could drop relayed host messages is gone.
    assert "event.source !== parentWin" not in html


# ---- widget pull path (Krea pattern) ----
# Claude Desktop strips structuredContent from the tool-result it pushes into
# the widget iframe, so the widget pulls its data itself via a host-relayed
# tools/call to an app-only tool whose response carries the full payload.

def test_widget_data_tool_returns_payload_on_both_channels(mela_db):
    out = server.get_recipe_widget_data(1)
    assert isinstance(out, CallToolResult)
    payload = out.structured_content
    assert payload["title"] == "Lemon Chicken"
    # The same payload also rides a JSON text block, so the widget can recover
    # it even if the host strips structuredContent from call responses too.
    assert json.loads(out.content[0].text) == payload

def test_widget_data_tool_not_found(mela_db):
    out = server.get_recipe_widget_data(999)
    assert out.structured_content == {"not_found": True, "recipe_id": 999}
    assert json.loads(out.content[0].text)["not_found"] is True

def test_widget_data_tool_is_app_only():
    # visibility=["app"] keeps the tool (and its base64-bearing content) off the
    # model-facing path: only the widget iframe may call it.
    tool = next(
        t for t in asyncio.run(server.mcp.list_tools())
        if t.name == "get_recipe_widget_data"
    )
    ui = (tool.meta or {})["ui"]
    assert ui["visibility"] == ["app"]
    assert ui["resourceUri"] == server.RECIPE_WIDGET_URI

def test_widget_data_tool_dispatch_through_sdk(mela_db):
    # Drive the pull tool through the SDK's real call path — the exact route the
    # host relays the widget's tools/call through — and check the wire shape.
    result = asyncio.run(server.mcp.call_tool("get_recipe_widget_data", {"recipe_id": 1}))
    assert isinstance(result, CallToolResult)
    wire = result.model_dump(mode="json", by_alias=True)
    assert wire["structuredContent"]["title"] == "Lemon Chicken"
    assert json.loads(wire["content"][0]["text"])["title"] == "Lemon Chicken"

def test_widget_data_tool_output_schema_is_none():
    # CallToolResult passthrough for the pull tool too: no output schema means
    # convert_result never rewrites the payload the widget depends on.
    tool = server.mcp._tool_manager.get_tool("get_recipe_widget_data")
    assert tool.output_schema is None

def test_get_recipe_model_content_is_markdown_not_json(mela_db):
    # The model-facing tool keeps markdown content (no base64, not JSON).
    out = server.get_recipe(1)
    assert out.content[0].text.startswith("# Lemon Chicken")
    assert "base64" not in out.content[0].text

def test_recipe_widget_html_has_pull_mechanism():
    # Pins the Krea pull pattern in the widget: a widget-initiated tools/call
    # for the app-only data tool, correlated by id through a pending map, with
    # recipe_id captured from the tool-input notification.
    html = server._WIDGET_HTML
    assert "tools/call" in html
    assert "get_recipe_widget_data" in html
    assert "pendingRequests" in html
    assert "ui/notifications/tool-input" in html
    assert "recipe_id" in html


def test_get_recipe_output_schema_is_none():
    # Pins the CallToolResult passthrough: a structured output schema would make
    # convert_result validate/rewrite our result. Guards against SDK drift.
    tool = server.mcp._tool_manager.get_tool("get_recipe")
    assert tool.output_schema is None

def test_get_recipe_returns_structured_content(mela_db):
    # Payload delivered unconditionally (no Apps capability gate), so a bound
    # widget host always receives the recipe data.
    out = server.get_recipe(1)

    assert isinstance(out, CallToolResult)
    assert isinstance(out.content[0], TextContent)
    assert "Lemon Chicken" in out.content[0].text

    payload = out.structured_content
    assert payload["title"] == "Lemon Chicken"
    assert "Dinner" in payload["tags"]
    assert isinstance(payload["images"], list)
    for uri in payload["images"]:
        assert uri.startswith("data:image/jpeg;base64,")
    # No base64 image blobs leak into the model-facing text content.
    assert "base64" not in out.content[0].text

def test_get_recipe_always_returns_call_tool_result(mela_db):
    # Unified return: no separate non-Apps list path; always a CallToolResult
    # carrying structured_content, so a widget host never renders an empty card.
    out = server.get_recipe(3)
    assert isinstance(out, CallToolResult)
    assert out.structured_content["title"] == "Chocolate Cake"

def test_get_recipe_dispatch_through_sdk(mela_db):
    # Drive the tool through the SDK's real call path (convert_result applied)
    # and inspect the serialized wire result.
    result = asyncio.run(server.mcp.call_tool("get_recipe", {"recipe_id": 1}))

    assert isinstance(result, CallToolResult)
    wire = result.model_dump(mode="json", by_alias=True)

    # structuredContent (camelCase) reaches the widget with the recipe fields.
    assert "structuredContent" in wire
    payload = wire["structuredContent"]
    assert payload["title"] == "Lemon Chicken"

    # Model-facing text never carries base64 image blobs.
    text = " ".join(b["text"] for b in wire["content"] if b.get("type") == "text")
    assert "base64" not in text

    if not sips_missing:
        assert any(
            uri.startswith("data:image/jpeg;base64,") for uri in payload["images"]
        )

def test_convert_result_passthrough_locks_structured_content():
    # Independent of dispatch: a CallToolResult with structured_content and no
    # output_schema passes through convert_result untouched.
    from mcp.server.mcpserver.utilities.func_metadata import func_metadata

    def _fn() -> list: ...
    meta = func_metadata(_fn)
    assert meta.output_schema is None

    src = CallToolResult(
        content=[TextContent(type="text", text="hi")],
        structured_content={"title": "X", "images": ["data:image/jpeg;base64,AAA"]},
    )
    out = meta.convert_result(src)
    assert out is src
    assert out.structured_content["title"] == "X"
