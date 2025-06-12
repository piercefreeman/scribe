"""Tests for PageContext functionality and consolidated logic."""

from pathlib import Path

import pytest

from scribe.context import PageContext


class TestPageContext:
    """Test PageContext class functionality."""

    @pytest.fixture
    def base_context(self):
        """Create a base PageContext for testing."""
        return PageContext(
            source_path=Path("test.md"),
            relative_path=Path("test.md"),
            output_path=Path("test.html"),
            raw_content="",
            content="",
        )

    def test_generate_slug_from_text_basic(self):
        """Test basic slug generation from text."""
        assert PageContext.generate_slug_from_text("Hello World") == "hello-world"
        assert (
            PageContext.generate_slug_from_text("My Article Title")
            == "my-article-title"
        )
        assert PageContext.generate_slug_from_text("Simple") == "simple"

    def test_generate_slug_from_text_special_chars(self):
        """Test slug generation with special characters."""
        assert (
            PageContext.generate_slug_from_text("API v2.1: User Auth")
            == "api-v21-user-auth"
        )
        assert (
            PageContext.generate_slug_from_text("Python & Django!") == "python-django"
        )
        assert (
            PageContext.generate_slug_from_text("Title with *italics*")
            == "title-with-italics"
        )
        assert PageContext.generate_slug_from_text("File (2024).txt") == "file-2024txt"

    def test_generate_slug_from_text_edge_cases(self):
        """Test slug generation edge cases."""
        assert PageContext.generate_slug_from_text("") == ""
        assert PageContext.generate_slug_from_text("   ") == ""
        assert PageContext.generate_slug_from_text("!!!") == ""
        assert PageContext.generate_slug_from_text("---") == ""
        assert PageContext.generate_slug_from_text("a") == "a"

    def test_generate_slug_from_text_multiple_hyphens(self):
        """Test slug generation removes multiple consecutive hyphens."""
        assert PageContext.generate_slug_from_text("Hello -- World") == "hello-world"
        assert PageContext.generate_slug_from_text("API --- v2") == "api-v2"
        assert (
            PageContext.generate_slug_from_text("Test---Multiple---Hyphens")
            == "test-multiple-hyphens"
        )

    def test_generate_slug_from_text_leading_trailing_hyphens(self):
        """Test slug generation removes leading/trailing hyphens."""
        assert PageContext.generate_slug_from_text("-Hello World-") == "hello-world"
        assert PageContext.generate_slug_from_text("--Start") == "start"
        assert PageContext.generate_slug_from_text("End--") == "end"

    def test_extract_title_from_content_basic(self, base_context):
        """Test basic title extraction from content."""
        base_context.content = "# My Title\nThis is content."
        title, content = base_context.extract_title_from_content()

        assert title == "My Title"
        assert content == "This is content."

    def test_extract_title_from_content_various_header_levels(self, base_context):
        """Test title extraction with different header levels."""
        test_cases = [
            ("# H1 Title\nContent", "H1 Title"),
            ("## H2 Title\nContent", "H2 Title"),
            ("### H3 Title\nContent", "H3 Title"),
            ("#### H4 Title\nContent", "H4 Title"),
            ("##### H5 Title\nContent", "H5 Title"),
            ("###### H6 Title\nContent", "H6 Title"),
        ]

        for content_input, expected_title in test_cases:
            base_context.content = content_input
            title, content = base_context.extract_title_from_content()
            assert title == expected_title
            assert content == "Content"

    def test_extract_title_from_content_with_whitespace(self, base_context):
        """Test title extraction handles whitespace correctly."""
        base_context.content = "#    Spaced Title   \nContent here."
        title, content = base_context.extract_title_from_content()

        assert title == "Spaced Title"
        assert content == "Content here."

    def test_extract_title_from_content_complex_title(self, base_context):
        """Test title extraction with complex title content."""
        base_context.content = (
            "# API v2.1: User Authentication (2024)\nContent follows."
        )
        title, content = base_context.extract_title_from_content()

        assert title == "API v2.1: User Authentication (2024)"
        assert content == "Content follows."

    def test_extract_title_from_content_empty_content_after(self, base_context):
        """Test title extraction with empty content after title."""
        base_context.content = "# Just a Title\n"
        title, content = base_context.extract_title_from_content()

        assert title == "Just a Title"
        assert content == ""

    def test_extract_title_from_content_only_title(self, base_context):
        """Test title extraction when content is only a title."""
        base_context.content = "# Only Title"
        title, content = base_context.extract_title_from_content()

        assert title == "Only Title"
        assert content == ""

    def test_extract_title_from_content_multiple_lines(self, base_context):
        """Test title extraction preserves multiple lines after title."""
        base_context.content = "# Title Here\n\nParagraph one.\n\nParagraph two."
        title, content = base_context.extract_title_from_content()

        assert title == "Title Here"
        assert content == "\nParagraph one.\n\nParagraph two."

    def test_extract_title_from_content_unicode(self, base_context):
        """Test title extraction with unicode characters."""
        base_context.content = (
            "# 📚 Learn Python: データ構造とアルゴリズム\nContent with unicode."
        )
        title, content = base_context.extract_title_from_content()

        assert title == "📚 Learn Python: データ構造とアルゴリズム"
        assert content == "Content with unicode."

    @pytest.mark.parametrize(
        "invalid_content",
        [
            "",  # Empty content
            "   \n  \n  ",  # Only whitespace
            "This is not a title\nContent here.",  # No hash
            "Some text # Not a title\nContent.",  # Hash not at start
            "#\nContent here.",  # Empty title after hash
            "#    \nContent here.",  # Only whitespace after hash
            "# \nContent here.",  # Single space after hash
        ],
    )
    def test_extract_title_from_content_errors(self, base_context, invalid_content):
        """Test that invalid content raises appropriate errors."""
        base_context.content = invalid_content

        with pytest.raises(ValueError) as exc_info:
            base_context.extract_title_from_content()

        error_message = str(exc_info.value)
        assert any(
            keyword in error_message
            for keyword in ["empty", "must start with", "Invalid title format"]
        )

    def test_slug_generation_integration_with_title(self, base_context):
        """Test that slug generation works correctly with extracted titles."""
        base_context.content = "# My Great Article\nContent here."
        title, _ = base_context.extract_title_from_content()
        slug = base_context.generate_slug_from_text(title)

        assert slug == "my-great-article"

    def test_slug_generation_integration_complex_title(self, base_context):
        """Test slug generation with complex title."""
        base_context.content = "# API v2.1: User Authentication (2024)!\nContent here."
        title, _ = base_context.extract_title_from_content()
        slug = base_context.generate_slug_from_text(title)

        assert slug == "api-v21-user-authentication-2024"

    def test_context_initialization_uses_consolidated_slug_logic(self):
        """Test that context initialization uses the consolidated slug logic."""
        # Test with title
        ctx = PageContext(
            source_path=Path("test.md"),
            relative_path=Path("test-file.md"),
            output_path=Path("test.html"),
            raw_content="",
            content="",
            title="My Great Title!",
        )

        # Should use title for slug generation with consolidated logic
        assert ctx.slug == "my-great-title"

    def test_context_initialization_fallback_to_filename(self):
        """Test that context initialization falls back to filename for slug."""
        ctx = PageContext(
            source_path=Path("test.md"),
            relative_path=Path("my-file-name.md"),
            output_path=Path("test.html"),
            raw_content="",
            content="",
        )

        # Should use filename for slug generation with consolidated logic
        assert ctx.slug == "my-file-name"

    def test_context_initialization_respects_frontmatter_slug(self):
        """Test that context initialization respects frontmatter slug."""
        from scribe.context import FrontmatterData

        ctx = PageContext(
            source_path=Path("test.md"),
            relative_path=Path("test-file.md"),
            output_path=Path("test.html"),
            raw_content="",
            content="",
            frontmatter=FrontmatterData(slug="custom-slug"),
            title="My Great Title!",
        )

        # Should use frontmatter slug over generated slug
        assert ctx.slug == "custom-slug"
