"""The error contract as a caller experiences it: masked bugs, unmasked AppToolError, retryable."""

import pytest
from fastmcp import Client, FastMCP

from mcpserver.errors import AppToolError, ErrorCode


async def a_bug() -> str:
    """A tool that forgot the contract."""
    raise ValueError("internal detail nobody should read")


async def a_known_failure() -> str:
    """A tool that raised the tool error the caller is meant to act on."""
    raise AppToolError(ErrorCode.NOT_FOUND, "No note is stored under `topic='gone'`. Call `notes_list`.")


def build_server() -> FastMCP:
    server = FastMCP("contract", mask_error_details=True)
    server.tool(a_bug)
    server.tool(a_known_failure)
    return server


async def test_a_bug_is_replaced_by_a_generic_message() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("a_bug", {}, raise_on_error=False)

    text = result.content[0].text
    assert result.is_error
    assert "internal detail" not in text
    assert "ValueError" not in text


async def test_an_app_tool_error_reaches_the_caller_verbatim() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("a_known_failure", {}, raise_on_error=False)

    assert "[NOT_FOUND]" in result.content[0].text
    assert "topic='gone'" in result.content[0].text


@pytest.mark.parametrize(
    ("retryable", "expected"),
    [(True, "[BACKEND_UNAVAILABLE, retryable]"), (False, "[BACKEND_UNAVAILABLE]")],
)
def test_retryability_is_visible_in_the_message(retryable: bool, expected: str) -> None:
    err = AppToolError(ErrorCode.BACKEND_UNAVAILABLE, "The backend is starting up.", retryable=retryable)

    assert str(err).startswith(expected)
    assert err.retryable is retryable
