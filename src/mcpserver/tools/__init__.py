"""Tool registration entrypoint.

The only place that knows about the MCP server. Each group -- the three data sources, and the
feedback tool -- is registered only when its flag is on: an unregistered tool is the one kind of
"disabled" the protocol guarantees, unlike tag or visibility filtering, which a later call can undo.

Every tool is a plain function, so none of them carries a registration wrapper. Those that need a
service take it through `Depends`; `send_feedback` needs none.
"""

from fastmcp import FastMCP

from mcp.types import ToolAnnotations

from ..settings import Settings
from .myservice.tools import tool1 #, tool2
# OR ---
# from .myservice.tool1 import tool1
# from .myservice.tool2 import tool2



# Les tools sont consultatifs, ne modifient pas leur environnement
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    openWorldHint=False,
    idempotentHint=True,
)

def register_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register the tools."""

    mcp.tool(tool1, annotations=READ_ONLY)
    #mcp.tool(tool2, annotations=READ_ONLY)
