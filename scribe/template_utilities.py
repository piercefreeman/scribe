"""
Utilities mounted and callable within Jinja.

"""
from collections import defaultdict

from scribe.note import Note


def filter_tag(
    notes: list[Note],
    tag_values: str | list[str],
    offset: int = 0,
    limit: int | None = None,
):
    """
    Filter for the inclusion/exclusion of some tag. Excluded tags can be prefixed
    with an exclimation point to note that they should be excluded.
    """
    if isinstance(tag_values, str):
        tag_values = [tag_values]

    tag_whitelist = {tag for tag in tag_values if not tag.startswith("!")}
    tag_blacklist = {tag.lstrip("!") for tag in tag_values if tag.startswith("!")}

    if tag_whitelist:
        notes = [
            note
            for note in notes
            if len(set(note.metadata.tags) & set(tag_whitelist)) > 0
        ]
    if tag_blacklist:
        notes = [
            note
            for note in notes
            if len(set(note.metadata.tags) & set(tag_blacklist)) == 0
        ]

    if offset:
        notes = notes[offset:]
    if limit:
        notes = notes[:limit]

    return notes


def group_by_month(notes: list[Note]) -> dict[str, list[Note]]:
    """
    Group a flat list of Notes by the month and year of publication.

    """
    notes = sorted(notes, key=lambda note: note.metadata.date, reverse=True)

    by_month = defaultdict(list)

    for note in notes:
        by_month[f"{note.metadata.date.month} / {note.metadata.date.year}"].append(note)

    return dict(by_month)
