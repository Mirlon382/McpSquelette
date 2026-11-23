"""Shared test scaffolding.

Every test talks to a real FastMCP app over the real protocol (`fastmcp.Client`); what is stubbed
is the outside world, never the server. `build_test_server` is the seam: it builds the same
application `mcpserver.server` builds, but with an `httpx.MockTransport` in place of the network.
"""

import httpx
import pytest

from mcpserver.lifespan import build_lifespan
from mcpserver.server import create_mcp
from mcpserver.settings import Settings

TEST_SETTINGS = Settings(_env_file=None)

WIKI_ARTICLE = {
    "title": "Ada Lovelace",
    "extract": "Ada Lovelace was an English mathematician and writer.",
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
}


def build_test_server(handler: httpx.MockTransport) -> object:
    """The production app, with this test's fake transport in place of the network."""
    return create_mcp(TEST_SETTINGS, lifespan=build_lifespan(TEST_SETTINGS, transport=handler))


def wikipedia_handler(request: httpx.Request) -> httpx.Response:
    """Answer like Wikipedia does: one article, one 404, one broken answer."""
    path = request.url.path
    if path.endswith("/Ada_Lovelace"):
        return httpx.Response(200, json=WIKI_ARTICLE)
    if path.endswith("/Broken_JSON"):
        return httpx.Response(200, text="<html>not json</html>")
    if path.endswith("/Server_Error"):
        return httpx.Response(503, text="upstream is down")
    return httpx.Response(404, json={"title": "Not found."})


@pytest.fixture
def wiki_server() -> object:
    """A server whose Wikipedia calls are answered by `wikipedia_handler`, not by the network."""
    return build_test_server(httpx.MockTransport(wikipedia_handler))


@pytest.fixture
def fresh_server() -> object:
    """A server with no recorded calls and an empty note store."""
    return build_test_server(httpx.MockTransport(wikipedia_handler))
