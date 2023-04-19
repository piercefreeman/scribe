from scribe.note import NoteStatus


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
