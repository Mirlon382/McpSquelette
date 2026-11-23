"""The write example's storage: an in-memory note store, created by the lifespan.

It is deliberately boring — one process, one list, lost on restart. It exists to show where
state belongs once a tool starts changing something: in the lifespan, next to the HTTP client,
so it is created once and can be replaced in a test. Swap it for a database client and the
tools do not change.
"""

import asyncio
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Note:
    """One stored note."""

    topic: str
    text: str


@dataclass
class NotesStore:
    """Notes held in memory, guarded by a lock so two concurrent calls cannot interleave."""

    _notes: list[Note] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def add(self, note: Note) -> int:
        """Append a note and return how many the store now holds."""
        async with self._lock:
            self._notes.append(note)
            return len(self._notes)

    async def list(self, topic: str | None = None) -> list[Note]:
        """Every note, or only those filed under `topic`."""
        async with self._lock:
            if topic is None:
                return list(self._notes)
            return [note for note in self._notes if note.topic == topic]
