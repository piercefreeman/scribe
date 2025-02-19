from scribe.footnotes import FootnoteParser
from scribe.tests.common import create_test_note


def test_has_footnotes():
    """Test detection of footnotes in text."""
    assert FootnoteParser.has_footnotes("This has a [^1] footnote")
    assert FootnoteParser.has_footnotes("This has a [^1]: definition")
    assert not FootnoteParser.has_footnotes("This has no footnotes")
    assert not FootnoteParser.has_footnotes("This has [1] but not a footnote")


def test_find_references():
    """Test finding footnote references in text."""
    text = create_test_note(
        header="Test References",
        body="""Here is a[^1] footnote and here is[^2] another one.
And here's [^10] a bigger number."""
    )
    refs = FootnoteParser.find_references(text)
    assert len(refs) == 3
    assert [ref[0] for ref in refs] == ["1", "2", "10"]
    # Positions should be in ascending order
    assert refs[0][1] < refs[1][1] < refs[2][1]


def test_find_definitions():
    """Test finding footnote definitions in text."""
    text = create_test_note(
        header="Test Definitions",
        body="""[^1]: First footnote
[^2]: Second footnote
with multiple lines
[^10]: Bigger number footnote"""
    )
    defs = FootnoteParser.find_definitions(text)
    assert len(defs) == 3
    assert [d[0] for d in defs] == ["1", "2", "10"]
    assert defs[0][1] == "First footnote"
    assert defs[1][1] == "Second footnote\nwith multiple lines"
    assert defs[2][1] == "Bigger number footnote"


def test_create_renumbering_map():
    """Test creation of renumbering map based on reference positions."""
    refs = [
        ("10", 50),  # Third in position
        ("1", 10),  # First in position
        ("5", 30),  # Second in position
    ]
    number_map = FootnoteParser.create_renumbering_map(refs)
    assert number_map == {"1": "1", "5": "2", "10": "3"}


def test_reorder_complex():
    """Test reordering of complex footnotes with multi-digit numbers."""
    text = create_test_note(
        header="Test Complex",
        body="""First[^10], second[^2], third[^1].

[^1]: Third note
[^2]: Second note
[^10]: First note"""
    )
    expected = create_test_note(
        header="Test Complex",
        body="""First[^1], second[^2], third[^3].

[^1]: First note
[^2]: Second note
[^3]: Third note"""
    )
    assert FootnoteParser.reorder(text) == expected


def test_reorder_with_multiline_definitions():
    """Test reordering of footnotes with multi-line definitions."""
    text = create_test_note(
        header="Test Multiline",
        body="""First[^2], second[^1].

[^2]: This is a multi-line
footnote definition
[^1]: Single line definition"""
    )
    expected = create_test_note(
        header="Test Multiline",
        body="""First[^1], second[^2].

[^1]: This is a multi-line
footnote definition
[^2]: Single line definition"""
    )
    assert FootnoteParser.reorder(text) == expected


def test_no_footnotes():
    """Test handling of text without footnotes."""
    text = create_test_note(
        header="No Footnotes",
        body="This text has no footnotes"
    )
    assert FootnoteParser.reorder(text) == text


def test_references_without_definitions():
    """Test handling of text with references but no definitions."""
    text = create_test_note(
        header="Missing Definitions",
        body="This has a[^1] reference but no definition"
    )
    assert FootnoteParser.reorder(text) == text


def test_definitions_without_references():
    """Test handling of text with definitions but no references."""
    text = create_test_note(
        header="Missing References",
        body="""Just some text

[^1]: A definition without reference"""
    )
    assert FootnoteParser.reorder(text) == text


def test_reorder_definitions_order():
    """Test that footnote definitions are reordered to match their numerical order."""
    text = create_test_note(
        header="Test Reordering",
        body="""Here is a[^2] footnote and here is[^1] another one.

[^2]: Second footnote
[^1]: First footnote"""
    )
    expected = create_test_note(
        header="Test Reordering",
        body="""Here is a[^1] footnote and here is[^2] another one.

[^1]: Second footnote
[^2]: First footnote"""
    )
    assert FootnoteParser.reorder(text) == expected

    # Test with non-sequential numbers
    text = create_test_note(
        header="Test Non-sequential",
        body="""First[^10], second[^2], third[^5].

[^5]: Third note
[^10]: First note
[^2]: Second note"""
    )
    expected = create_test_note(
        header="Test Non-sequential",
        body="""First[^1], second[^2], third[^3].

[^1]: First note
[^2]: Second note
[^3]: Third note"""
    )
    assert FootnoteParser.reorder(text) == expected
