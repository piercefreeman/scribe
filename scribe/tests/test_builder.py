from pathlib import Path
from tempfile import TemporaryDirectory

from pytest import fixture

from website_builder.builder import WebsiteBuilder
from website_builder.note import Note


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
