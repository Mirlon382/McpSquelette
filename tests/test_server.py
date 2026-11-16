"""End to end over the real protocol: the registered tool is listed and answers with the output model."""

from fastmcp import Client

from mcpserver.server import mcp


async def test_the_example_tool_is_registered_with_its_schema() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    assert "tool1" in tools
    tool = tools["tool1"]
    assert tool.description  # the docstring is the description the model reads
    assert list(tool.input_schema["properties"]) == ["word"]


async def test_the_example_tool_answers_with_the_output_model() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("tool1", {"word": "hello"})

    assert result.data.returned_phrase == "Votre choix : hello"


async def test_the_example_tool_is_annotated_read_only() -> None:
    async with Client(mcp) as client:
        tool = (await client.list_tools())[0]

    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False


async def test_an_invalid_argument_is_rejected_by_the_schema() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("tool1", {"word": "not-a-choice"}, raise_on_error=False)

    assert result.is_error
