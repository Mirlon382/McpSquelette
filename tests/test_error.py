"""The error contract: what a caller reads, and what the attributes hold."""

from mcpserver.errors import AppToolError, ErrorCode


def test_message_carries_the_code_and_the_reason() -> None:
    err = AppToolError(ErrorCode.INVALID_INPUT, "`word` must be one of hello, world or !.")

    assert str(err).startswith("[INVALID_INPUT]")
    assert "`word`" in str(err)


def test_retryable_is_marked_in_the_message() -> None:
    err = AppToolError(ErrorCode.BACKEND_UNAVAILABLE, "The backend is starting up.", retryable=True)

    assert "[BACKEND_UNAVAILABLE, retryable]" in str(err)
    assert err.retryable is True


def test_attributes_survive_for_tests_and_logging() -> None:
    err = AppToolError(ErrorCode.NOT_FOUND, "No unit matches that SIREN.")

    assert err.code is ErrorCode.NOT_FOUND
    assert err.retryable is False


def test_it_is_a_tool_error_so_the_message_is_not_masked() -> None:
    from fastmcp.exceptions import ToolError

    assert isinstance(AppToolError(ErrorCode.INTERNAL_ERROR, "boom"), ToolError)
