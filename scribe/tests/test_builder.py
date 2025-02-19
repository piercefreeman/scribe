from pathlib import Path

from scribe.builder import WebsiteBuilder
from scribe.metadata import BuildMetadata, NoteStatus
from scribe.models import TemplateArguments
from scribe.note import Note

SCRATCH_NOTE = """
# Scratch Note

This is a scratch note.
"""

DRAFT_NOTE = """
# Draft Note

meta:
    date: September 27, 2022
    status: draft

This is a draft note.
"""


def test_exclude_scratch(builder: WebsiteBuilder, note_directory: Path):
    """
    Test that excluded notes are not published
    """
    (note_directory / "scratch_note.md").write_text(SCRATCH_NOTE)
    (note_directory / "draft_note.md").write_text(DRAFT_NOTE)

    notes = builder.get_notes(note_directory)
    assert len(notes) == 1

    assert notes[0].metadata.status == NoteStatus.DRAFT


def test_skip_hidden_directories(builder: WebsiteBuilder, note_directory: Path):
    """
    Test that files in hidden directories (starting with .) are skipped
    """
    # Create a hidden directory
    hidden_dir = note_directory / ".scribe_backups"
    hidden_dir.mkdir()

    # Create a note in the hidden directory
    (hidden_dir / "hidden_note.md").write_text(DRAFT_NOTE)

    # Create a note in the main directory
    (note_directory / "visible_note.md").write_text(DRAFT_NOTE)

    notes = builder.get_notes(note_directory)
    assert len(notes) == 1
    assert notes[0].path.name == "visible_note.md"


def test_get_notes_empty_directory(builder: WebsiteBuilder, note_directory: Path):
    result = builder.get_notes(note_directory)
    assert result == []


def test_build_static_no_overwrite_existing_file(builder: WebsiteBuilder, tmpdir: str):
    static_path = Path(tmpdir) / "static"
    static_path.mkdir()

    test_file = static_path / "test.txt"
    test_file.write_text("Original content")
    builder.build_static(static_path, BuildMetadata())

    assert test_file.read_text() == "Original content"


def test_build_rss_no_draft_notes_in_feed(
    builder: WebsiteBuilder, tmpdir: str, draft_note: Note, published_note: Note
):
    notes = [
        published_note,
        draft_note,
    ]
    rss_path = Path(tmpdir) / "rss"
    rss_path.mkdir()
    builder.build_rss(notes, rss_path)
    rss_file = rss_path / "rss.xml"
    assert "DRAFT" not in rss_file.read_text()


def test_get_paginated_arguments_no_notes(builder: WebsiteBuilder):
    notes: list[Note] = []
    limit = 5
    result = list(builder.get_paginated_arguments(notes, limit))
    assert result == []


def test_get_paginated_arguments_single_page(builder: WebsiteBuilder, published_note: Note):
    notes = [published_note] * 3
    limit = 5
    result = list(builder.get_paginated_arguments(notes, limit))
    assert len(result) == 1

    note = result[0]
    assert note.notes is not None
    assert len(note.notes) == 3


def test_get_paginated_arguments_multiple_pages(builder: WebsiteBuilder, published_note: Note):
    notes = [published_note] * 7
    limit = 5
    result = list(builder.get_paginated_arguments(notes, limit))
    assert len(result) == 2
    assert result[0].offset == 0
    assert result[1].offset == 5


def test_augment_page_directions_no_offset_limit(builder: WebsiteBuilder):
    arguments = TemplateArguments()
    result = builder.augment_page_directions(arguments)
    assert result.directions is None


def test_augment_page_directions_first_page(builder: WebsiteBuilder, published_note: Note):
    arguments = TemplateArguments(notes=[published_note] * 10, offset=0, limit=5)
    result = builder.augment_page_directions(arguments)
    assert result.directions is not None
    assert len(result.directions) == 1
    assert result.directions[0].direction == "next"


def test_augment_page_directions_middle_page(builder: WebsiteBuilder, published_note: Note):
    arguments = TemplateArguments(notes=[published_note] * 15, offset=5, limit=5)
    result = builder.augment_page_directions(arguments)
    assert result.directions is not None
    assert len(result.directions) == 2
    assert result.directions[0].direction == "previous"
    assert result.directions[1].direction == "next"
