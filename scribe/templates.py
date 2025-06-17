"""Functions made available to global templates"""

from datetime import datetime
from typing import Any

from scribe.context import PageContext
from scribe.predicates import PredicateMatcher


class NotesAccessor:
    """Provides access to notes with predicate filtering for templates."""

    def __init__(
        self,
        notes: list[PageContext],
        predicate_matcher: PredicateMatcher,
    ):
        # Sort notes by date (newest first), then by title (A-Z) for tie-breaking
        def get_sort_key(note: PageContext) -> tuple[datetime, str]:
            # Get the date
            if note.date_data and note.date_data.parsed:
                date = note.date_data.parsed
            else:
                # Use a very old date for notes without date_data
                date = datetime(1900, 1, 1)

            # Get the title for tie-breaking (case-insensitive)
            title = (note.title or note.source_path.stem or "").lower()

            # Return negative date for descending order,
            # positive title for ascending order
            return (-date.timestamp(), title)

        self.notes = sorted(notes, key=get_sort_key)
        self.predicate_matcher = predicate_matcher

    def all(self) -> list[dict[str, Any]]:
        """Return all notes as template-friendly dictionaries."""
        return [self._note_to_dict(note) for note in self.notes]

    def filter(self, *predicates: str) -> list[dict[str, Any]]:
        """Filter notes by predicates and return as template-friendly dictionaries."""
        filtered_notes = []
        for note in self.notes:
            if self.predicate_matcher.matches_predicates(note, predicates):
                filtered_notes.append(self._note_to_dict(note))
        return filtered_notes

    def _note_to_dict(self, ctx: PageContext) -> dict[str, Any]:
        """Convert PageContext to template-friendly dictionary."""
        return ctx.model_dump(mode="json")
