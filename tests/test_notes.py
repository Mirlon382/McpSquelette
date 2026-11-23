"""The write example: state lives in the lifespan, so a fresh app starts empty."""

from fastmcp import Client


async def test_notes_are_filed_under_their_topic(fresh_server) -> None:
    async with Client(fresh_server) as client:
        await client.call_tool("notes_add", {"topic": "work", "text": "Send the invoice"})
        await client.call_tool("notes_add", {"topic": "shopping", "text": "Flour"})
        work = await client.call_tool("notes_list", {"topic": "work"})
        everything = await client.call_tool("notes_list", {})

    assert [note.text for note in work.data.notes] == ["Send the invoice"]
    assert everything.data.count == 2


async def test_notes_are_returned_oldest_first(fresh_server) -> None:
    async with Client(fresh_server) as client:
        for text in ["first", "second", "third"]:
            await client.call_tool("notes_add", {"topic": "order", "text": text})
        listed = await client.call_tool("notes_list", {"topic": "order"})

    assert [note.text for note in listed.data.notes] == ["first", "second", "third"]


async def test_the_schema_refuses_a_note_that_is_too_long(fresh_server) -> None:
    """What the schema can validate, the schema validates: no hand-written length check needed."""
    async with Client(fresh_server) as client:
        result = await client.call_tool("notes_add", {"topic": "big", "text": "x" * 2001}, raise_on_error=False)

    assert result.is_error
    assert "2000" in result.content[0].text
