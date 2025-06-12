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
        # Sort notes by date, treating None dates as oldest
        def get_sort_date(note: PageContext) -> datetime:
            if note.date_data and note.date_data.parsed:
                return note.date_data.parsed
            # Use a very old date for notes without date_data
            return datetime(1900, 1, 1)

        self.notes = sorted(notes, key=get_sort_date, reverse=True)
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
