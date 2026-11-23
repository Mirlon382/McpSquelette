"""End to end over the real protocol: what the server publishes, and how it answers."""

from fastmcp import Client

from mcpserver.server import mcp


async def test_the_example_tools_are_registered_with_their_schemas() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    # Subset, not equality: scaffolding your own tool must not turn this test red.
    assert {"wikipedia_summary", "notes_add", "notes_list"} <= set(tools)
    # A Depends parameter never reaches the input schema: the model only sees real arguments.
    assert list(tools["wikipedia_summary"].input_schema["properties"]) == ["title"]
    assert list(tools["notes_add"].input_schema["properties"]) == ["topic", "text"]
    for tool in tools.values():
        assert tool.description  # the docstring is the description the model reads


async def test_the_write_tool_is_annotated_as_a_write_and_the_readers_as_reads() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    assert tools["notes_add"].annotations.read_only_hint is False
    assert tools["notes_list"].annotations.read_only_hint is True
    assert tools["wikipedia_summary"].annotations.read_only_hint is True
    assert tools["wikipedia_summary"].annotations.destructive_hint is False


async def test_the_write_tool_round_trips_through_the_store() -> None:
    async with Client(mcp) as client:
        added = await client.call_tool("notes_add", {"topic": "shopping", "text": "Two kilos of flour"})
        listed = await client.call_tool("notes_list", {"topic": "shopping"})

    assert added.structured_content["total_notes"] == 1
    assert listed.data.count == 1
    assert listed.data.notes[0].text == "Two kilos of flour"


async def test_an_empty_result_is_a_result_not_an_error() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("notes_list", {"topic": "nothing-here"}, raise_on_error=False)

    assert result.is_error is False
    assert result.data.count == 0


async def test_an_invalid_argument_is_rejected_by_the_schema() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("notes_add", {"topic": "", "text": "x"}, raise_on_error=False)

    assert result.is_error
