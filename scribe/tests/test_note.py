from re import match

from scribe.note import Note, NoteStatus


def test_title():
    text = """
    # Top Header
    Some content
    ## Other Header
    """

    assert Note(text=text, path="/fake-path.md").title == "Top Header"


def test_webpage_path():
    text = """
    ## Valid Header 123
    Some content
    """

    assert Note(text=text, path="/fake-path.md").webpage_path == "valid-header-123"

    text = """
    # Partially || Invalid Header
    Some content
    """

    assert Note(text=text, path="/fake-path.md").webpage_path == "partially-invalid-header"


def test_get_markdown():
    text = (
        "# Header\n"
        "## Subheader\n"
        "Content\n"
    )

    find_pattern = (
        "<h2>Subheader</h2>\n"
        "<p>Content</p>"
    )

    assert match(find_pattern, Note(text=text, path="/fake-path.md").get_html())


def test_published():
    text = """
    # Header
    Some content
    """

    assert Note(text=text, path="/fake-path.md").metadata.status == NoteStatus.SCRATCH

    text = """
    # Header

    meta:
        status: publish
        date: February 2, 2022

    Some content
    """

    assert Note(text=text, path="/fake-path.md").metadata.status == NoteStatus.PUBLISHED
