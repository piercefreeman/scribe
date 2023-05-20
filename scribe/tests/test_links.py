from scribe.links import local_to_remote_links
from scribe.note import Note


def test_local_link(note_directory):
    text = "#Header\nthis is a [local path](./Local.md) other phrase ()"

    local_mapping = {"Local": "remote-path"}

    new_text = local_to_remote_links(
        Note.from_text(text=text, path=note_directory / "note.md"), local_mapping
    )
    assert new_text == "this is a [local path](remote-path) other phrase ()"


def test_remote_link_http(note_directory):
    text = "# Header\nthis is a [remote path](http://google.com) other phrase ()"
    local_mapping = {}

    new_text = local_to_remote_links(
        Note.from_text(text=text, path=note_directory / "note.md"), local_mapping
    )
    new_text == text


def test_remote_link_www(note_directory):
    text = "# Header\nthis is a [remote path](www.google.com) other phrase ()"
    local_mapping = {}

    new_text = local_to_remote_links(
        Note.from_text(text=text, path=note_directory / "note.md"), local_mapping
    )
    new_text == text
