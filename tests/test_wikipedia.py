"""The API-backed tool, against a fake Wikipedia: every failure mode the tool promises to map.

No test here touches the network: `conftest.build_test_server` hands the app an
`httpx.MockTransport`, which is the same code path production takes with a real client.
"""

from fastmcp import Client

CASES = [
    ("Ada Lovelace", "Ada Lovelace", True),
    ("Nobody At All", "NOT_FOUND", False),
    ("Server Error", "UPSTREAM_ERROR", False),
    ("Broken JSON", "PARSE_ERROR", True),
]


async def test_a_known_article_comes_back_as_the_output_model(wiki_server) -> None:
    async with Client(wiki_server) as client:
        result = await client.call_tool("wikipedia_summary", {"title": "Ada Lovelace"})

    assert result.data.title == "Ada Lovelace"
    assert "mathematician" in result.data.extract
    assert result.data.url.endswith("Ada_Lovelace")


async def test_every_failure_is_a_readable_coded_message(wiki_server) -> None:
    async with Client(wiki_server) as client:
        for title, marker, _ in CASES:
            result = await client.call_tool("wikipedia_summary", {"title": title}, raise_on_error=False)
            if marker == "Ada Lovelace":
                assert result.is_error is False
                continue
            assert result.is_error, title
            text = result.content[0].text
            # The code reaches the caller; so does the parameter they have to fix.
            assert marker in text, text
            assert "title=" in text, text


async def test_a_transient_failure_is_marked_retryable(wiki_server) -> None:
    async with Client(wiki_server) as client:
        result = await client.call_tool("wikipedia_summary", {"title": "Broken JSON"}, raise_on_error=False)

    assert "[PARSE_ERROR, retryable]" in result.content[0].text
