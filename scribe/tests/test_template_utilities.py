import datetime

import pytest

from scribe.note import Note, NoteMetadata
from scribe.template_utilities import filter_tag, group_by_month


@pytest.fixture
def note_with_tags():
    metadata = NoteMetadata(tags=["tag1", "tag2"], date=datetime.datetime(2022, 1, 1))
    return Note(
        text="test note",
        metadata=metadata,
        title="test title",
        simple_content="test content",
    )


@pytest.fixture
def note_with_date():
    metadata = NoteMetadata(date=datetime.datetime(2022, 1, 1))
    return Note(
        text="test note",
        metadata=metadata,
        title="test title",
        simple_content="test content",
    )


@pytest.fixture
def multiple_notes():
    metadata1 = NoteMetadata(tags=["tag1", "tag2"], date=datetime.datetime(2022, 2, 1))
    note1 = Note(
        text="test note 1",
        title="test title",
        simple_content="test content",
        metadata=metadata1,
    )
    metadata2 = NoteMetadata(tags=["tag2", "tag3"], date=datetime.datetime(2022, 1, 1))
    note2 = Note(
        text="test note 2",
        title="test title",
        simple_content="test content",
        metadata=metadata2,
    )
    metadata3 = NoteMetadata(tags=["tag3", "tag4"], date=datetime.datetime(2022, 1, 3))
    note3 = Note(
        text="test note 3",
        title="test title",
        simple_content="test content",
        metadata=metadata3,
    )
    return [note1, note2, note3]


# Tests for the filter_tag function
def test_filter_tag_with_empty_notes_list():
    assert filter_tag([], "tag") == []


def test_filter_tag_with_one_note_and_include_tag(note_with_tags):
    assert filter_tag([note_with_tags], "tag1") == [note_with_tags]


def test_filter_tag_with_one_note_and_exclude_tag(note_with_tags):
    assert filter_tag([note_with_tags], "!tag1") == []


def test_filter_tag_with_multiple_notes_and_include_tag(multiple_notes):
    assert filter_tag(multiple_notes, "tag2") == multiple_notes[:2]


def test_filter_tag_with_multiple_notes_and_exclude_tag(multiple_notes):
    assert filter_tag(multiple_notes, "!tag1") == multiple_notes[1:]


def test_filter_tag_with_offset(multiple_notes):
    assert filter_tag(multiple_notes, "tag2", offset=1) == [multiple_notes[1]]


def test_filter_tag_with_limit(multiple_notes):
    assert filter_tag(multiple_notes, "tag3", limit=2) == multiple_notes[1:]


# Tests for the group_by_month function
def test_group_by_month_with_empty_notes_list():
    assert group_by_month([]) == {}


def test_group_by_month_with_one_note(note_with_date):
    assert group_by_month([note_with_date]) == {"1 / 2022": [note_with_date]}


def test_group_by_month_with_multiple_notes(multiple_notes):
    expected_result = {
        "2 / 2022": [multiple_notes[0]],
        "1 / 2022": [multiple_notes[2], multiple_notes[1]],
    }
    assert group_by_month(multiple_notes) == expected_result
