"""Pydantic schemas for the skeleton's tools.

Inputs are `Annotated` aliases so the description and the examples travel with the type, and every
tool answers with a `BaseModel` rather than a dict: FastMCP derives the output schema from it, and
each field's description is what the model reads when it decides how to use a result.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

MAX_RESULT_COUNT = 10

# ----------------------------------------------------------------------------------------------------------------------
# Enumerations ---------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------


class Tool1Choice(StrEnum):
    """The closed set of values `tool1` accepts, so a bad value fails here rather than downstream."""

    HELLO = "hello"
    WORLD = "world"
    EXCLAM = "!"


# ----------------------------------------------------------------------------------------------------------------------
# Tool parameters ------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------

Tool1Input = Annotated[
    Tool1Choice,
    Field(
        description="Which word to echo back: 'hello', 'world' or '!'.",
        examples=["hello"],
    ),
]

# ----------------------------------------------------------------------------------------------------------------------
# Result models --------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------


class OutputPhrase(BaseModel):
    """What `tool1` returns."""

    returned_phrase: str = Field(description="The sentence built from the chosen word.")
