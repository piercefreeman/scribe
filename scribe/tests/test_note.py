from re import match
from pathlib import Path
import pytest
from datetime import datetime

from scribe.metadata import NoteStatus
from scribe.note import Note


def test_title():
    text = """
    # Top Header
    Some content
    ## Other Header
    """

    assert Note.from_text(text=text, path="/fake-path.md").title == "Top Header"


def test_webpage_path():
    text = """
    ## Valid Header 123
    Some content
    """

    assert Note.from_text(text=text, path="/fake-path.md").webpage_path == "valid-header-123"

    text = """
    # Partially || Invalid Header
    Some content
    """

    assert (
        Note.from_text(text=text, path="/fake-path.md").webpage_path == "partially-invalid-header"
    )


def test_get_markdown():
    text = "# Header\n## Subheader\nContent\n"

    find_pattern = "<h2>Subheader</h2>\n<p>Content</p>"

    assert match(find_pattern, Note.from_text(text=text, path="/fake-path.md").get_html())


def test_published():
    text = """
    # Header
    Some content
    """

    assert Note.from_text(text=text, path="/fake-path.md").metadata.status == NoteStatus.SCRATCH

    text = """
    # Header

    meta:
        status: publish
        date: February 2, 2022

    Some content
    """

    assert Note.from_text(text=text, path="/fake-path.md").metadata.status == NoteStatus.PUBLISHED


def test_auto_fix_missing_title(tmp_path):
    """Test that a file with no title gets auto-fixed with a stub title."""
    test_file = tmp_path / "test.md"
    content = """Some content without a title
    
    This should get a title added."""
    
    test_file.write_text(content)
    
    # The note creation should add a title
    note = Note.from_file(test_file)
    
    # Verify the backup was created
    backup_dir = tmp_path / ".scribe_backups"
    assert backup_dir.exists()
    backup_files = list(backup_dir.glob("*.md"))
    assert len(backup_files) == 1
    assert backup_files[0].read_text() == content
    
    # Verify the new content
    new_content = test_file.read_text()
    today = datetime.now().strftime('%Y-%m-%d')
    assert new_content.startswith(f"# Draft Note {today}\n\n")
    assert content in new_content
    
    # Verify the note object
    assert note.title == f"Draft Note {today}"
    assert note.metadata.status == NoteStatus.SCRATCH


def test_auto_fix_missing_metadata(tmp_path):
    """Test that a file with title but no metadata gets auto-fixed with stub metadata."""
    test_file = tmp_path / "test.md"
    content = """# Existing Title
    
    Some content without metadata block.
    This should get metadata added."""
    
    test_file.write_text(content)
    
    # The note creation should add metadata
    note = Note.from_file(test_file)
    
    # Verify the backup was created
    backup_dir = tmp_path / ".scribe_backups"
    assert backup_dir.exists()
    backup_files = list(backup_dir.glob("*.md"))
    assert len(backup_files) == 1
    assert backup_files[0].read_text() == content
    
    # Verify the new content
    new_content = test_file.read_text()
    today = datetime.now().strftime('%B %-d, %Y')
    assert "# Existing Title" in new_content
    assert "meta:" in new_content
    assert f"date: {today}" in new_content
    assert "status: draft" in new_content
    
    # Verify the note object
    assert note.title == "Existing Title"
    assert note.metadata.status == NoteStatus.DRAFT
    assert note.metadata.date.strftime('%B %-d, %Y') == today
