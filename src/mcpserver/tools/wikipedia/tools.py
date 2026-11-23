"""Wikipedia: one read-only tool that calls an external API.

This is the shape to copy for any API-backed tool: take the client from `Depends`, map every way
the call can fail onto an `AppToolError` whose message tells the model what to do next, and return
a model.
"""

import httpx
from fastmcp.dependencies import Depends

from ...errors import AppToolError, ErrorCode
from ...models.wikipedia import ArticleSummary, ArticleTitle
from ...utils.http import Http, get_http

SUMMARY_ENDPOINT = "https://en.wikipedia.org/api/rest_v1/page/summary/"


async def wikipedia_summary(title: ArticleTitle, http: Http = Depends(get_http)) -> ArticleSummary:
    """Read the plain-text summary of one English Wikipedia article.

    Call this when the user asks what something is and you need a short, citable description.
    Pass the exact article title: a near miss returns NOT_FOUND, not a list of suggestions.
    """
    url = SUMMARY_ENDPOINT + title.replace(" ", "_")

    try:
        response = await http.client.get(url)
    except httpx.TimeoutException as exc:
        raise AppToolError(
            ErrorCode.BACKEND_UNAVAILABLE,
            f"Wikipedia did not answer within the timeout for `title={title!r}`. Retry the same call.",
            retryable=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise AppToolError(
            ErrorCode.BACKEND_UNAVAILABLE,
            f"Wikipedia could not be reached for `title={title!r}`. Retry in a moment.",
            retryable=True,
        ) from exc

    if response.status_code == 404:
        raise AppToolError(
            ErrorCode.NOT_FOUND,
            f"No English Wikipedia article is titled `title={title!r}`. Check the spelling and use the "
            "article name itself, not a question.",
        )
    if response.status_code >= 400:
        raise AppToolError(
            ErrorCode.UPSTREAM_ERROR,
            f"Wikipedia answered {response.status_code} for `title={title!r}`. Try a different title.",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppToolError(
            ErrorCode.PARSE_ERROR,
            f"Wikipedia's answer for `title={title!r}` was not readable JSON. Retry the same call.",
            retryable=True,
        ) from exc

    return ArticleSummary(
        title=payload.get("title", title),
        extract=payload.get("extract", ""),
        url=payload.get("content_urls", {}).get("desktop", {}).get("page", ""),
    )
