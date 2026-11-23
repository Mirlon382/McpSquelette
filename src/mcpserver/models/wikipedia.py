"""Schemas for the Wikipedia examples.

Inputs are `Annotated` aliases so the description and the examples travel with the type, and every
tool answers with a `BaseModel` rather than a dict: FastMCP derives the output schema from it, and
each field's description is what the model reads when it decides how to use a result.
"""

from typing import Annotated

from pydantic import BaseModel, Field

# ----------------------------------------------------------------------------------------------------------------------
# Tool parameters ------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------

ArticleTitle = Annotated[
    str,
    Field(
        description=(
            "Exact English Wikipedia article title, not a search phrase: 'Ada Lovelace', not 'who was ada lovelace'."
        ),
        examples=["Ada Lovelace"],
        min_length=1,
        max_length=200,
    ),
]

# ----------------------------------------------------------------------------------------------------------------------
# Result models --------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------


class ArticleSummary(BaseModel):
    """What `wikipedia_summary` returns."""

    title: str = Field(description="The article title as Wikipedia resolved it.")
    extract: str = Field(description="Plain-text summary of the article, usually two or three sentences.")
    url: str = Field(description="Canonical desktop URL of the article.")
