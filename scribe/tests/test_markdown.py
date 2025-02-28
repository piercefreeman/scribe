from scribe.markdown import MarkdownParser


def test_find_markdown_links():
    """Test finding markdown links in text."""
    text = """
Here are some links:
- [External Link](https://example.com)
- [Another Link](http://test.com)
- [Local Link](./local.md)
- [WWW Link](www.google.com)
- [Escaped Link](https://example.com/\\[escaped\\])
- Not a [link] and not a (link)
- \\[Escaped](not-a-link)
"""
    links = MarkdownParser.find_markdown_links(text)
    assert links == [
        ("External Link", "https://example.com"),
        ("Another Link", "http://test.com"),
        ("Local Link", "./local.md"),
        ("WWW Link", "www.google.com"),
        ("Escaped Link", "https://example.com/\\[escaped\\]"),
    ]


def test_find_markdown_images():
    """Test finding markdown image links in text."""
    text = r"""
Here are some images:
![Alt Text](image.jpg)
![Another Image](./subfolder/image.png)
![Remote Image](https://example.com/image.jpg)
Not an image: [Link](image.jpg)
\![Escaped Image](not-an-image.jpg)
"""
    images = MarkdownParser.find_markdown_images(text)
    assert images == [
        ("Alt Text", "image.jpg"),
        ("Another Image", "./subfolder/image.png"),
        ("Remote Image", "https://example.com/image.jpg"),
    ]


def test_find_html_images():
    """Test finding HTML image tags in text."""
    text = """
Here are some HTML images:
<img src="image1.jpg" alt="Image 1"/>
<img src='image2.png' alt='Image 2' class="large"/>
<img src="https://example.com/image.jpg"/>
Not an image: <imgsrc="fake.jpg">
<img alt="No source">
"""
    images = MarkdownParser.find_html_images(text)
    assert images == [
        "image1.jpg",
        "image2.png",
        "https://example.com/image.jpg",
    ]


def test_is_external_url():
    """Test detection of external URLs."""
    assert MarkdownParser.is_external_url("https://example.com")
    assert MarkdownParser.is_external_url("http://example.com")
    assert MarkdownParser.is_external_url("www.example.com")
    assert not MarkdownParser.is_external_url("./local/file.md")
    assert not MarkdownParser.is_external_url("../relative/path")
    assert not MarkdownParser.is_external_url("just-a-file.txt")


def test_normalize_path():
    """Test path normalization."""
    assert MarkdownParser.normalize_path("./image.jpg") == "image.jpg"
    assert MarkdownParser.normalize_path("../image.jpg") == "image.jpg"
    assert MarkdownParser.normalize_path("subfolder/image.jpg") == "image.jpg"
    assert MarkdownParser.normalize_path("image.jpg") == "image.jpg"


def test_extract_referenced_images():
    """Test extracting all referenced images from text."""
    text = """
Here are various image formats:
![Markdown Image](image1.jpg)
<img src="image2.png" alt="HTML Image"/>
![Another Image](./subfolder/image3.jpg)
<img src='image4.png'/>
![Remote Image](https://example.com/image5.jpg)
Not an image: [Link](not-an-image.jpg)
"""
    images = MarkdownParser.extract_referenced_images(text)
    assert images == {
        "image1.jpg",
        "image2.png",
        "image3.jpg",
        "image4.png",
        "image5.jpg",
    }


def test_extract_external_urls():
    """Test extracting external URLs from text."""
    text = """
Here are some links:
[External](https://example.com)
[Another](http://test.com)
[Local](./local.md)
[WWW](www.google.com)
[Escaped](https://example.com/\\[escaped\\])
"""
    urls = MarkdownParser.extract_external_urls(text)
    assert urls == {
        "https://example.com",
        "http://test.com",
        "www.google.com",
        "https://example.com/[escaped]",
    }


def test_find_footnote_references():
    """Test finding footnote references in text."""
    text = """
Here are some footnotes[^1] and [^note-1] and [^UPPERCASE].
Not footnotes: [^] [^1]: or [not^1]
Here's another[^2] reference.
"""
    refs = MarkdownParser.find_footnote_references(text)
    assert refs == ["1", "note-1", "UPPERCASE", "2"]


def test_find_footnote_definitions():
    """Test finding footnote definitions in text."""
    text = """
Here's a note[^1] and another[^2].

[^1]: This is a single line footnote
[^2]: This is a multi-line footnote
    with an indented continuation.

More text here.

[^3]: Another footnote
with unindented continuation.

[not^4]: Not a footnote
"""
    defs = MarkdownParser.find_footnote_definitions(text)
    assert defs == [
        ("1", "This is a single line footnote"),
        ("2", "This is a multi-line footnote\n    with an indented continuation."),
        ("3", "Another footnote\nwith unindented continuation."),
    ]


def test_has_footnotes():
    """Test detection of footnotes in text."""
    # Test with no footnotes
    text_no_footnotes = """
Regular text with [links](url) and ![images](img.jpg)
but no footnotes.
"""
    assert not MarkdownParser.has_footnotes(text_no_footnotes)

    # Test with only references
    text_only_refs = """
Text with footnote references[^1] and [^note] but no definitions.
"""
    assert MarkdownParser.has_footnotes(text_only_refs)

    # Test with only definitions
    text_only_defs = """
Text without references.

[^1]: But with a definition.
"""
    assert MarkdownParser.has_footnotes(text_only_defs)

    # Test with both
    text_complete = """
Text with a reference[^1] and its definition.

[^1]: The definition.
"""
    assert MarkdownParser.has_footnotes(text_complete)

    # Test with invalid syntax
    text_invalid = """
Text with [^] and [^1: invalid syntax.
"""
    assert not MarkdownParser.has_footnotes(text_invalid)
