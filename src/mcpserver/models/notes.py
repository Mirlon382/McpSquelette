"""Schemas for the notes example: one write tool, one read tool, one store."""

from typing import Annotated

from pydantic import BaseModel, Field

MAX_TEXT_LENGTH = 2000

# ----------------------------------------------------------------------------------------------------------------------
# Tool parameters ------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------

NoteTopic = Annotated[
    str,
    Field(
        description="Short lowercase label the note is filed under, for example 'shopping'.",
        examples=["shopping"],
        min_length=1,
        max_length=40,
    ),
]

NoteText = Annotated[
    str,
    Field(
        description="The note itself, free text.",
        examples=["Two kilos of flour"],
        min_length=1,
        max_length=MAX_TEXT_LENGTH,
    ),
]

OptionalNoteTopic = Annotated[
    str | None,
    Field(
        description="Only return notes filed under this topic. Omit to return every note.",
        examples=["shopping"],
    ),
]

# ----------------------------------------------------------------------------------------------------------------------
# Result models --------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------


class NoteAdded(BaseModel):
    """What `notes_add` returns."""

    topic: str = Field(description="The topic the note was filed under.")
    text: str = Field(description="The text that was stored.")
    total_notes: int = Field(description="How many notes the store holds after this addition.")


class StoredNote(BaseModel):
    """One note, as read back by `notes_list`."""

    topic: str = Field(description="The topic the note is filed under.")
    text: str = Field(description="The stored text.")


class NoteList(BaseModel):
    """What `notes_list` returns."""

    notes: list[StoredNote] = Field(description="The matching notes, oldest first. Empty when nothing matches.")
    count: int = Field(description="Number of notes in `notes`.")
