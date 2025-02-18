from scribe.footnotes import FootnoteParser


def test_has_footnotes():
    """Test detection of footnotes in text."""
    assert FootnoteParser.has_footnotes("This has a [^1] footnote")
    assert FootnoteParser.has_footnotes("This has a [^1]: definition")
    assert not FootnoteParser.has_footnotes("This has no footnotes")
    assert not FootnoteParser.has_footnotes("This has [1] but not a footnote")


def test_find_references():
    """Test finding footnote references in text."""
    text = """
    Here is a[^1] footnote and here is[^2] another one.
    And here's [^10] a bigger number.
    """
    refs = FootnoteParser.find_references(text)
    assert len(refs) == 3
    assert [ref[0] for ref in refs] == ["1", "2", "10"]
    # Positions should be in ascending order
    assert refs[0][1] < refs[1][1] < refs[2][1]


def test_find_definitions():
    """Test finding footnote definitions in text."""
    text = """
    [^1]: First footnote
    [^2]: Second footnote
    with multiple lines
    [^10]: Bigger number footnote
    """
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


def test_reorder_simple():
    """Test reordering of simple footnotes."""
    text = """
    Here is a[^2] footnote and here is[^1] another one.

    [^2]: Second footnote
    [^1]: First footnote
    """
    expected = """
    Here is a[^1] footnote and here is[^2] another one.

    [^1]: Second footnote
    [^2]: First footnote
    """
    assert FootnoteParser.reorder(text) == expected


def test_reorder_complex():
    """Test reordering of complex footnotes with multi-digit numbers."""
    text = """
    First[^10], second[^2], third[^1].

    [^1]: Third note
    [^2]: Second note
    [^10]: First note
    """
    expected = """
    First[^1], second[^2], third[^3].

    [^3]: Third note
    [^2]: Second note
    [^1]: First note
    """
    assert FootnoteParser.reorder(text) == expected


def test_reorder_with_multiline_definitions():
    """Test reordering of footnotes with multi-line definitions."""
    text = """
    First[^2], second[^1].

    [^2]: This is a multi-line
    footnote definition
    [^1]: Single line definition
    """
    expected = """
    First[^1], second[^2].

    [^1]: This is a multi-line
    footnote definition
    [^2]: Single line definition
    """
    assert FootnoteParser.reorder(text) == expected


def test_no_footnotes():
    """Test handling of text without footnotes."""
    text = "This text has no footnotes"
    assert FootnoteParser.reorder(text) == text


def test_references_without_definitions():
    """Test handling of text with references but no definitions."""
    text = "This has a[^1] reference but no definition"
    assert FootnoteParser.reorder(text) == text


def test_definitions_without_references():
    """Test handling of text with definitions but no references."""
    text = """
    Just some text

    [^1]: A definition without reference
    """
    assert FootnoteParser.reorder(text) == text
