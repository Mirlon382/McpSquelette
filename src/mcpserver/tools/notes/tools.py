"""Notes: the write example.

A write tool is not different code from `wikipedia_summary` — it is a different *annotation* at
registration (`WRITE` in `tools/__init__.py`) and a description that says so out loud. A client
reads those hints to decide whether to ask the user first.
"""

from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.context import Context

from ...models.notes import NoteAdded, NoteList, NoteText, NoteTopic, OptionalNoteTopic, StoredNote
from ...notes_store import Note, NotesStore


def get_notes(ctx: Context = CurrentContext()) -> NotesStore:
    """The store the lifespan created."""
    return ctx.lifespan_context["notes"]


async def notes_add(
    topic: NoteTopic,
    text: NoteText,
    store: NotesStore = Depends(get_notes),
) -> NoteAdded:
    """Store one note under a topic. This writes data: the note is kept until the server restarts.

    Use it when the user asks to remember something. Call `notes_list` to read notes back.
    """
    # No length check here on purpose: `NoteText` already caps the length, so the schema rejects a
    # longer note before this function runs. Raise AppToolError only for what a schema cannot say.
    total = await store.add(Note(topic=topic, text=text))
    return NoteAdded(topic=topic, text=text, total_notes=total)


async def notes_list(topic: OptionalNoteTopic = None, store: NotesStore = Depends(get_notes)) -> NoteList:
    """List the stored notes, oldest first, optionally only those filed under one topic.

    This only reads. It returns an empty list, not an error, when nothing matches.
    """
    notes = await store.list(topic)
    return NoteList(
        notes=[StoredNote(topic=note.topic, text=note.text) for note in notes],
        count=len(notes),
    )
