from pathlib import Path
from tempfile import TemporaryDirectory

from pytest import fixture

from scribe.builder import WebsiteBuilder
from scribe.note import Note, NoteStatus


@fixture()
def builder():
    return WebsiteBuilder()

@fixture()
def note_directory():
    with TemporaryDirectory() as directory:
        yield Path(directory)

def test_local_link(builder, note_directory):
    text = "#Header\nthis is a [local path](./Local.md) other phrase ()"

    local_mapping = {
        "Local": "remote-path"
    }

    new_text = builder.local_to_remote_links(
        Note(text=text, path=note_directory / "note.md"),
        local_mapping
    )
    assert new_text == "this is a [local path](remote-path) other phrase ()"

def test_remote_link_http(builder, note_directory):
    text = "# Header\nthis is a [remote path](http://google.com) other phrase ()"
    local_mapping = {}

    new_text = builder.local_to_remote_links(
        Note(text=text, path=note_directory / "note.md"),
        local_mapping
    )
    new_text == text

def test_remote_link_www(builder, note_directory):
    text = "# Header\nthis is a [remote path](www.google.com) other phrase ()"
    local_mapping = {}

    new_text = builder.local_to_remote_links(
        Note(text=text, path=note_directory / "note.md"),
        local_mapping
    )
    new_text == text

def test_exclude_scratch(builder, note_directory):
    """
    Test that excluded notes are not published
    """
    with open(note_directory / "scratch_note.md", "w") as file:
        file.write(
            """
            # Scratch Note

            This is a scratch note.
            """
        )

    with open(note_directory / "draft_note.md", "w") as file:
        file.write(
            """
            # Draft Note

            meta:
                date: September 27, 2022
                status: draft

            This is a draft note.
            """
        )

    notes = builder.get_notes(note_directory)
    assert len(notes) == 1

    assert notes[0].metadata.status == NoteStatus.DRAFT
