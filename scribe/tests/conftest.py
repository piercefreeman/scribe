from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scribe.builder import WebsiteBuilder
from scribe.metadata import NoteMetadata, NoteStatus
from scribe.note import Note


@pytest.fixture()
def builder():
    return WebsiteBuilder()


@pytest.fixture()
def note_directory():
    with TemporaryDirectory() as directory:
        yield Path(directory)


@pytest.fixture()
def draft_note():
    return Note(
        text="DRAFT_TEXT",
        title="DRAFT_TITLE",
        simple_content="DRAFT_CONTENT",
        metadata=NoteMetadata(date=datetime.now(), status=NoteStatus.DRAFT),
    )


@pytest.fixture()
def published_note():
    return Note(
        text="PUBLISHED_TEXT",
        title="PUBLISHED_TITLE",
        simple_content="PUBLISHED_CONTENT",
        metadata=NoteMetadata(date=datetime.now(), status=NoteStatus.PUBLISHED),
    )
