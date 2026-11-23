"""Scaffold one tool across the four files it touches, then leave it failing on purpose.

Usage (from the repository root):

    uv run python scripts/new_tool.py weather --write
    uv run python scripts/new_tool.py search --summary "Search the product catalogue."

What it writes:

    src/mcpserver/models/<name>.py          the input alias and the result model
    src/mcpserver/tools/<name>/tools.py     the tool function, raising a visible "not implemented"
    src/mcpserver/tools/<name>/__init__.py  empty, like every other tool package
    tests/test_<name>.py                    the protocol test that goes green once you fill the body
    src/mcpserver/tools/__init__.py         the import and the registration, appended

It does not invent your logic. It removes the three ways a new tool silently fails to appear:
forgetting the import, forgetting the registration, and forgetting the test.
"""

from __future__ import annotations

import argparse
import keyword
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "mcpserver"
TOOLS_INIT = SRC / "tools" / "__init__.py"

MODEL_TEMPLATE = '''"""Schemas for the `{name}` tool."""

from typing import Annotated

from pydantic import BaseModel, Field

# One alias per argument. Every Field needs a description: it is the schema the model reads.
{name_camel}Query = Annotated[
    str,
    Field(
        description="What the model must pass. Say what a valid value looks like here.",
        examples=["example value"],
        min_length=1,
    ),
]

# Add one alias per extra argument, in snake_case, and one parameter per alias on the function.


class {name_camel}Result(BaseModel):
    """What `{name}` returns."""

    answer: str = Field(description="Say what this holds, or replace it with your real fields.")
'''

TOOL_TEMPLATE = '''"""{summary}"""

from ...errors import AppToolError, ErrorCode
from ...models.{name} import {name_camel}Query, {name_camel}Result


async def {name}(query: {name_camel}Query) -> {name_camel}Result:
    """{summary}

    Call this when ... Say what the tool does, when a model should reach for it, and what it
    returns. The docstring is the description the model reads, so it is not decoration.
    """
    # TODO: replace this body. While it raises, the tool is visible and honest about being a stub;
    # deleting the raise without writing the real logic is the only way to ship a broken tool.
    raise AppToolError(
        ErrorCode.INTERNAL_ERROR,
        "`{name}` is not implemented yet: replace the body in src/mcpserver/tools/{name}/tools.py.",
    )
'''

TEST_TEMPLATE = '''"""End to end over the real protocol: the `{name}` tool is listed, and answers with its model."""

import pytest
from fastmcp import Client

from mcpserver.server import mcp


async def test_{name}_is_registered_with_its_schema() -> None:
    async with Client(mcp) as client:
        tools = {{tool.name: tool for tool in await client.list_tools()}}

    assert "{name}" in tools
    tool = tools["{name}"]
    assert tool.description
    # The arguments the model sees. Update this list when you add a parameter.
    assert list(tool.input_schema["properties"]) == ["query"]


async def test_{name}_answers_with_its_result_model() -> None:
    # TODO: implement the tool, delete the skip line, and assert on your real result fields.
    pytest.skip("`{name}` is still a stub: fill in the body, then finish this test.")

    async with Client(mcp) as client:
        result = await client.call_tool("{name}", {{"query": "example value"}})

    assert result.data.answer
'''


def to_camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold a new tool in this McpSquelette server.")
    parser.add_argument("name", help="Tool name in snake_case, e.g. `weather_now`.")
    parser.add_argument(
        "--summary",
        default=None,
        help="One sentence describing what the tool does. Defaults to a placeholder.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Register with WRITE annotations instead of READ_ONLY.",
    )
    return parser.parse_args(argv)


def validate(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        sys.exit(f"error: `{name}` must be snake_case (lowercase letters, digits, underscores).")
    if keyword.iskeyword(name):
        sys.exit(f"error: `{name}` is a Python keyword.")
    if (SRC / "tools" / name).exists() or (SRC / "models" / f"{name}.py").exists():
        sys.exit(f"error: `{name}` already exists; pick another name or delete the old files.")
    return name


def register(name: str, write: bool) -> None:
    """Append the import and the registration to tools/__init__.py, refusing to guess."""
    text = TOOLS_INIT.read_text()
    marker = f"from .{name}.tools import {name}"
    if marker in text:
        sys.exit(f"error: tools/__init__.py already imports `{name}`.")

    lines = text.splitlines(keepends=True)
    imports = [index for index, line in enumerate(lines) if line.startswith("from .")]
    if not imports:
        sys.exit("error: no relative imports in tools/__init__.py; add the registration by hand.")
    lines.insert(imports[-1] + 1, marker + "\n")

    # ruff (I001) wants the relative imports sorted, and a line appended at the end is not.
    imports = [index for index, line in enumerate(lines) if line.startswith("from .")]
    block = sorted((lines[index] for index in imports), key=str.strip)
    for index, line in zip(imports, block, strict=True):
        lines[index] = line

    annotations = "WRITE" if write else "READ_ONLY"
    if "def register_tools" not in "".join(lines):
        sys.exit("error: register_tools() not found in tools/__init__.py; add the registration by hand.")
    lines.append(f"    mcp.tool({name}, annotations={annotations})\n")
    TOOLS_INIT.write_text("".join(lines))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    name = validate(args.name)
    name_camel = to_camel(name)
    summary = args.summary or f"Do the one thing `{name}` exists for."

    (SRC / "tools" / name).mkdir(parents=True)
    (SRC / "tools" / name / "__init__.py").write_text("")
    (SRC / "models" / f"{name}.py").write_text(MODEL_TEMPLATE.format(name=name, name_camel=name_camel))
    (SRC / "tools" / name / "tools.py").write_text(
        TOOL_TEMPLATE.format(name=name, name_camel=name_camel, summary=summary)
    )
    (REPO_ROOT / "tests" / f"test_{name}.py").write_text(TEST_TEMPLATE.format(name=name))
    register(name, args.write)

    print(
        f"""\nScaffolded `{name}`:

  src/mcpserver/models/{name}.py
  src/mcpserver/tools/{name}/tools.py
  tests/test_{name}.py
  src/mcpserver/tools/__init__.py   (import + registration appended)

Next:
  1. Replace the body of `{name}` in src/mcpserver/tools/{name}/tools.py.
  2. Add a parameter: one alias in models/{name}.py, one argument on the function.
  3. Fill the test's happy path (it fails now, on purpose), then run:
       uv run pytest -q tests/test_{name}.py
       uv run ruff check . && uv run ruff format --check .

Delete the example tools (wikipedia_summary, notes_*) when your own are in."""
    )


if __name__ == "__main__":
    main()
