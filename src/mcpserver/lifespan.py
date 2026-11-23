"""Process-wide resources: opened once at startup, closed once at shutdown.

A tool never builds its own HTTP client. It asks for one through `utils/http.get_http`,
which reads the client this lifespan yields. That is what keeps connections pooled, keeps the
timeout and the User-Agent in one place, and lets a test hand in `httpx.MockTransport`.

FastMCP wants a lifespan that takes the server, so the settings are closed over here rather
than passed to the decorator.
"""

from collections.abc import AsyncIterator

import httpx
from fastmcp import FastMCP
from fastmcp.server.lifespan import Lifespan, lifespan

from .notes_store import NotesStore
from .settings import Settings


def build_lifespan(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> Lifespan:
    """Build the lifespan. `transport` is a seam for tests: production passes nothing.

    Whatever is yielded here is reachable from a tool as `ctx.lifespan_context["name"]`; keep the
    keys stable, they are the contract between this file and every tool.
    """

    @lifespan
    async def _lifespan(_server: FastMCP) -> AsyncIterator[dict[str, object]]:
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.http_user_agent},
            transport=transport,
        ) as http:
            yield {"http": http, "notes": NotesStore()}

    return _lifespan
