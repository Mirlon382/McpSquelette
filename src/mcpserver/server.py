"""Entrypoint: builds the settings, the lifespan and the MCP application, then serves it.

Two transports, one command: `MCP_TRANSPORT=http` (the default) serves Streamable HTTP on `/mcp`;
`MCP_TRANSPORT=stdio` runs the same tools over pipes, for a client that launches the process.
"""

import logging
from textwrap import dedent

import uvicorn
from fastmcp import FastMCP
from fastmcp.server.lifespan import Lifespan
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import LoggingMiddleware
from fastmcp.server.middleware.rate_limiting import SlidingWindowRateLimitingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware

from .lifespan import build_lifespan
from .logging import build_logging_config, configure_logging
from .settings import Settings, load_settings
from .tools import register_tools
from .utils.client_host import resolve_client_host

settings = load_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

# Sent to the client in the handshake. Only what belongs to no single tool: which tool to call, and
# when, is in the tool descriptions, where it reaches the model even when a client drops these
# instructions. Keep this text true for whatever tools you register.
INSTRUCTIONS = dedent("""
    Call a tool only when the request needs something you do not already have, and fill every
    argument the input schema marks as required. Each tool's description says whether it only
    reads or also changes something on this server.

    A failed call answers with a message that begins with an error code in brackets: read the
    text, fix the argument it names, and only then call again.
""").strip()


def create_mcp(app_settings: Settings, lifespan: Lifespan | None = None) -> FastMCP:
    """Build the application.

    Tests call this with their own lifespan so no test reaches the network; production calls it
    with none and gets `build_lifespan` with the real settings.
    """
    server = FastMCP(
        app_settings.mcp_name,
        instructions=INSTRUCTIONS,
        # Only AppToolError messages reach the caller; anything else is a bug and is replaced
        # by a generic message.
        mask_error_details=True,
        lifespan=lifespan if lifespan is not None else build_lifespan(app_settings),
    )

    register_tools(server, app_settings)

    # Order matters: error handling first so it sees the whole chain, logging last so it records
    # what ran. Each middleware logs under its own `fastmcp.*` logger; set levels there to tune the
    # output. None of them logs how many results a tool returned. If empty results become hard to
    # diagnose, add an `on_call_tool` middleware that inspects the ToolResult, or have the tool
    # report it with `ctx.info`.
    server.add_middleware(
        # include_traceback puts the original cause in the server log, which is the only place it
        # is recoverable. transform_errors would promote our ToolErrors to JSON-RPC protocol errors
        # labelled "Internal error", losing is_error and the message the caller is meant to act on.
        ErrorHandlingMiddleware(
            transform_errors=False,
            include_traceback=True,
        ),
    )
    server.add_middleware(
        SlidingWindowRateLimitingMiddleware(
            max_requests=app_settings.rate_limit_max_requests,
            window_minutes=app_settings.rate_limit_window_minutes,
            get_client_id=resolve_client_host,
        ),
    )
    server.add_middleware(TimingMiddleware())
    server.add_middleware(LoggingMiddleware())
    return server


mcp = create_mcp(settings)

if settings.mcp_transport == "http" and settings.allowed_hosts == ["*"]:
    logger.warning("allowed_hosts is ['*']. Set ALLOWED_HOSTS before exposing the server publicly.")

# Enforced rather than "auto": this server is published under a real hostname, so it should check
# the one it was reached by instead of leaving the decision to a heuristic. Kept at module level so
# `uvicorn mcpserver.server:app` serves it too.
app = mcp.http_app(
    host_origin_protection=True,
    allowed_hosts=settings.allowed_hosts,
    allowed_origins=settings.allowed_origins,
)


def main() -> None:
    if settings.mcp_transport == "stdio":
        # The client owns the process: no port, no host guard, and no banner on the pipe.
        mcp.run(transport="stdio", show_banner=False)
        return

    uvicorn.run(
        app,
        host=settings.mcp_host,
        port=settings.mcp_port,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxy_hosts,
        log_config=build_logging_config(settings.log_level),
    )


if __name__ == "__main__":
    main()
