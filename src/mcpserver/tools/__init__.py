"""Tool registration entrypoint.

The only place that knows about the MCP server. Every tool is a plain function with no
registration wrapper, so a tool becomes visible -- and stays invisible -- in exactly one list.

Annotations travel with the registration, not the function: they tell the client whether a call
reads or writes, and a wrong `readOnlyHint` is worse than none, so set them per tool.
"""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..settings import Settings

# A group of tools lives in its own package: `tools/<yourservice>/tools.py`, then import from it
# here. One file per tool also works (`tools/myservice/mytool.py`) -- pick one and stay with it.
from .notes.tools import notes_add, notes_list
from .wikipedia.tools import wikipedia_summary

# Read-only: the tool answers a question and changes nothing, so a client may call it freely.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    openWorldHint=False,
    idempotentHint=True,
)

# Write: the tool keeps what it is given. destructiveHint is about losing data, not about
# changing it -- adding a note destroys nothing, so it stays False; a delete tool would set True.
WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=False,
    idempotentHint=False,
)


def register_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register every tool the server exposes.

    `settings` is here so a tool group can be switched on by configuration; register a tool only
    when its flag is on. An unregistered tool is the one kind of "disabled" the protocol
    guarantees, unlike tag or visibility filtering, which a later call can undo.
    """

    # Delete the next three lines and the two example packages once your own tools are in.
    mcp.tool(wikipedia_summary, annotations=READ_ONLY)
    mcp.tool(notes_add, annotations=WRITE)
    mcp.tool(notes_list, annotations=READ_ONLY)
