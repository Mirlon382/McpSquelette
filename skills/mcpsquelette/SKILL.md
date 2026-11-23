---
name: mcpsquelette
description: Add or change tools in an McpSquelette MCP server.
---

# Working in an McpSquelette server

An McpSquelette server is a plain FastMCP v4 application. Logging, configuration, rate limiting,
host/origin protection, the error contract, both transports and deployment are already there:
your work is the data and the tools.

Read this once, then follow **Adding a tool**. Everything else is here to be looked up when a step
surprises you.

## Adding a tool

Run the scaffolder from the repository root — it writes every file a tool touches, in the right
place, already wired:

```bash
uv run python scripts/new_tool.py weather_now --summary "Return the current weather for one city."
uv run python scripts/new_tool.py notes_add --write --summary "Store one note under a topic."
```

`--write` registers the tool with `WRITE` annotations instead of `READ_ONLY`. The generated tool
raises a visible "not implemented" `AppToolError` until you replace the body, and its test is
skipped until you finish it. A scaffolded repository still passes `ruff` and `pytest`; what it does
not do is pretend the tool works.

Then edit, in this order:

1. `src/mcpserver/models/<name>.py` — one `Annotated` alias per argument, one `BaseModel` for the
   result. Every `Field` gets a `description`; that text is the schema the model reads, not
   decoration.
2. `src/mcpserver/tools/<name>/tools.py` — `async def my_tool(arg: MyInput) -> MyResult`. The
   docstring is the tool description: say what it does, when to call it, what it returns.
3. `tests/test_<name>.py` — delete the `pytest.skip` line and assert on the real result fields.
4. Only if you skipped the scaffolder: `src/mcpserver/tools/__init__.py` — `mcp.tool(my_tool,
   annotations=READ_ONLY)`. Registration lives only there. Never decorate a tool in its own module,
   and never import a tool that is not registered: an unregistered tool is the only "disabled" the
   protocol guarantees.

A second argument is one more alias plus one more function parameter. Arguments are the keyword-only
fields of the schema, so a boolean is fine as a named field (`in_stock: bool`); a bare `True` at a
call site is not.

## Anything the tool needs arrives through `Depends`

Never a module-level global, and never a client built inside the tool. The lifespan
(`src/mcpserver/lifespan.py`) opens the HTTP client and the state store once; a dependency reads
them out:

```python
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.context import Context


def get_http(ctx: Context = CurrentContext()) -> Http:
    return Http(client=ctx.lifespan_context["http"])


async def my_tool(city: CityName, http: Http = Depends(get_http)) -> Weather:
    """..."""
    response = await http.client.get(f"https://api.example.com/weather/{city}")
```

Two traps, both of which look like they work:

- **A `Depends` that returns a bare `httpx.AsyncClient` fails on the second call** with
  `RuntimeError: Cannot open a client instance more than once` — FastMCP enters every context
  manager a dependency returns, per call. Return a plain wrapper (`utils/http.Http`) instead.
- **A client constructed inside the tool** is never closed, so every call leaks a connection pool.

`src/mcpserver/utils/http.py` and `src/mcpserver/tools/wikipedia/tools.py` are the working version;
copy them. A dependency parameter never appears in the input schema — the model sees only real
arguments.

Need a setting? Add it to `Settings` in `settings.py` and to `.env.example`, then read it from the
lifespan (build the client with it) or from `ctx.lifespan_context`. Settings are not passed to tools
one by one.

## Errors the caller will read

Raise `AppToolError(code, message, retryable=...)` from `mcpserver.errors`, never `ValueError`.
`mask_error_details=True` replaces any other exception with a generic message, so a bare `raise`
hides the reason from the caller — and a bug looks identical to a refusal.

- The message must name the offending parameter and what to do next; it is the whole answer.
- `retryable=True` renders `[BACKEND_UNAVAILABLE, retryable]`, so a client knows a retry is safe.
  Timeouts and connection failures are retryable; a 404 is not.
- Do not hand-check what the schema already enforces: `min_length`, `max_length`, `Literal`,
  `StrEnum` reject bad input before your function runs. Raise for what a schema cannot say — the
  upstream said no, the thing does not exist, the answer cannot be parsed.
- Answer with a model, not a `dict`: FastMCP derives the output schema from the return type. An
  empty list is a result, not an error.

## Annotations

A tool that only reads gets `READ_ONLY`. A tool that writes gets `WRITE` — or its own
`ToolAnnotations` with `readOnlyHint=False, destructiveHint=True, idempotentHint=False` when it can
lose data — and says so in its docstring. A wrong `readOnlyHint` is worse than none: the client uses
it to decide whether to ask the user first.

## Transports

`MCP_TRANSPORT=http` (the default) serves Streamable HTTP on `POST /mcp`. `MCP_TRANSPORT=stdio` runs
the same tools over pipes for a client that launches the process, which is what Claude Desktop and
most editors do:

```json
{"mcpServers": {"my-server": {"command": "uv", "args": ["run", "--directory", "/abs/path", "mcpserver"], "env": {"MCP_TRANSPORT": "stdio"}}}}
```

Nothing in a tool changes between the two.

## Verification, in this order

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -q                                  # protocol-level, no network
uv run mcpserver                                  # then: npx @modelcontextprotocol/inspector
```

The suite talks to the real app over the protocol through `fastmcp.Client(mcp)` — a test that calls
the function directly proves nothing about registration or schema. For a tool that calls an API, use
the seam in `tests/conftest.py`: `build_test_server(httpx.MockTransport(handler))` gives the same app
with the network replaced, so every branch of your error mapping is testable offline.

## Tool not listed? Check, in this order

1. Registered in `src/mcpserver/tools/__init__.py`? (The scaffolder does it; a by-hand tool often
   forgets.)
2. Its package imported there — an unused module is never executed.
3. The name collides with another tool (same `name` twice is silently one tool).
4. The server restarted: schemas are built at startup, there is no hot reload.

## Before shipping

- `ALLOWED_HOSTS` no longer `["*"]` for an HTTP deployment; `ALLOWED_ORIGINS` covers only real
  browser clients. Neither matters for `stdio`.
- `.env` is never committed; new settings exist in `.env.example` and in `Settings`.
- The example tools (`wikipedia_summary`, `notes_add`, `notes_list`) are deleted once your own are
  in — with their packages, their tests and their three registration lines.
- `uv.lock` is current (`uv lock` after editing dependencies), or the Docker build fails on
  `--locked`.
