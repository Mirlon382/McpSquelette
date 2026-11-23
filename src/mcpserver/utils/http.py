"""The outbound HTTP client, handed to a tool through `Depends`.

Read this file before writing your first tool that calls an API: it is the pattern, and it is
the one place where the obvious version is wrong.

Two traps, both silent until the second call:

1. `Depends(get_client)` where `get_client` returns a bare `httpx.AsyncClient` makes FastMCP open
   the client itself, per call. The second call fails with
   `RuntimeError: Cannot open a client instance more than once`.
2. Building a client inside the tool and never closing it leaks a connection pool per call.

So the client lives in the lifespan, and the dependency returns `Http` — a plain object FastMCP
does not try to open — wrapping the shared client.
"""

from dataclasses import dataclass

import httpx
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context


@dataclass(frozen=True)
class Http:
    """A borrowed client. Do not close it: the lifespan owns its lifetime."""

    client: httpx.AsyncClient


def get_http(ctx: Context = CurrentContext()) -> Http:
    """The client the lifespan opened. FastMCP resolves this before the tool runs."""
    return Http(client=ctx.lifespan_context["http"])
