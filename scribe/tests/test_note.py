from datetime import datetime
from re import match

from scribe.metadata import NoteStatus
from scribe.note import Note
from scribe.tests.common import create_test_note


def test_title():
    text = create_test_note(header="Top Header", body="Some content\n## Other Header")
    assert Note.from_text(text=text, path="/fake-path.md").title == "Top Header"


def test_webpage_path():
    text = create_test_note(header="Valid Header 123", body="Some content")
    assert Note.from_text(text=text, path="/fake-path.md").webpage_path == "valid-header-123"

    text = create_test_note(header="Partially || Invalid Header", body="Some content")
    assert (
        Note.from_text(text=text, path="/fake-path.md").webpage_path == "partially-invalid-header"
    )


def test_get_markdown():
    text = create_test_note(header="Header", body="## Subheader\nContent")
    find_pattern = "<h2>Subheader</h2>\n<p>Content</p>"
    assert match(find_pattern, Note.from_text(text=text, path="/fake-path.md").get_html())


def test_published():
    text = create_test_note(header="Header", body="Some content")
    assert Note.from_text(text=text, path="/fake-path.md").metadata.status == NoteStatus.DRAFT

    text = create_test_note(
        header="Header", body="Some content", meta={"status": "publish", "date": "February 2, 2022"}
    )
    assert Note.from_text(text=text, path="/fake-path.md").metadata.status == NoteStatus.PUBLISHED


def test_auto_add_missing_title(tmp_path):
    """Test that a file with no title gets auto-fixed with a stub title."""
    test_file = tmp_path / "test.md"
    content = "Some content without a title\n\nThis should get a title added."
    test_file.write_text(content)

    # The note creation should add a title
    note = Note.from_file(test_file)

    # Verify the backup was created. There should be two files, one with the original content
    # and one with the header but not the metadata
    backup_dir = tmp_path / ".scribe_backups"
    assert backup_dir.exists()
    backup_files = list(backup_dir.glob("*.md"))
    assert len(backup_files) == 2
    assert any(backup_file.read_text() == content for backup_file in backup_files)

    # Verify the new content matches what we expect
    today = datetime.now().strftime("%Y-%m-%d")

    # Verify the note object
    assert note.title == f"Draft Note {today}"
    assert note.metadata.status == NoteStatus.SCRATCH
    assert note.text == "Some content without a title\n\nThis should get a title added."


def test_auto_add_missing_metadata(tmp_path):
    """Test that a file with title but no metadata gets auto-fixed with stub metadata."""
    test_file = tmp_path / "test.md"

    # Initial content - just a title and body, no metadata
    content = (
        "# Existing Title\n\nSome content without metadata block.\nThis should get metadata added."
    )
    test_file.write_text(content)

    # The note creation should add metadata
    note = Note.from_file(test_file)

    # Verify the backup was created
    backup_dir = tmp_path / ".scribe_backups"
    assert backup_dir.exists()
    backup_files = list(backup_dir.glob("*.md"))
    assert len(backup_files) == 1
    assert backup_files[0].read_text() == content

    # Verify the new content matches what create_test_note would generate
    today = datetime.now().strftime("%B %-d, %Y")

    # Verify the note object
    assert note.title == "Existing Title"
    assert note.metadata.status == NoteStatus.SCRATCH
    assert note.metadata.date.strftime("%B %-d, %Y") == today
    assert note.text == "Some content without metadata block.\nThis should get metadata added."
