---
name: mcpsquelette
description: Use when adding, changing or debugging tools in an McpSquelette MCP server.
---

# Working in an McpSquelette server

An McpSquelette server is a plain FastMCP v4 application. The skeleton already does logging,
configuration, rate limiting, error masking and deployment: your work is the data and the tools.

## The three files a new tool touches

1. `src/mcpserver/models/<yourdomain>.py` — Pydantic models. One `Annotated` alias per input, one
   `BaseModel` per output. Every `Field` gets a `description`; that text is the schema the model
   reads, not decoration.
2. `src/mcpserver/tools/<yourservice>/tools.py` — `async def my_tool(arg: MyInput) -> MyOutput`.
   The docstring is the tool description: say what it does, when to call it, what it returns.
3. `src/mcpserver/tools/__init__.py` — `mcp.tool(my_tool, annotations=READ_ONLY)`. Registration
   lives only here. Never decorate a tool in its own module, and never import a tool that is not
   registered: an unregistered tool is the only "disabled" the protocol guarantees.

## Rules that are easy to get wrong

- Raise `AppToolError(code, message, retryable=...)`, never `ValueError`. `mask_error_details=True`
  replaces any other exception with a generic message, so a bare `raise` hides the reason from the
  caller. The message must name the offending parameter and what to do next.
- Answer with a model, not a `dict`: FastMCP derives the output schema from the return type.
- Tool arguments are keyword-only fields of the schema. Booleans are fine as named fields (FBT001/
  FBT002 are disabled for this reason); a bare `True` at a call site is not (FBT003).
- Anything the tool needs (HTTP client, credentials, settings) arrives through `Depends`, not a
  module-level global.
- A tool that only reads data gets `READ_ONLY`. A tool that writes gets its own annotations with
  `readOnlyHint=False, destructiveHint=True, idempotentHint=False` — and say so in the description.

## Verification, in this order

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
uv run python -m mcpserver.server          # then: npx @modelcontextprotocol/inspector
```

The suite talks to the real app over the protocol through `fastmcp.Client(mcp)` — a test that
calls the function directly does not prove the tool is registered or that its schema is right.

## Before shipping

- `ALLOWED_HOSTS` no longer `["*"]`; `ALLOWED_ORIGINS` covers only real browser clients.
- `.env` is never committed; new settings exist in `.env.example` and in `Settings`.
- `uv.lock` is current (`uv lock` after editing dependencies), or the Docker build fails on
  `--locked`.
