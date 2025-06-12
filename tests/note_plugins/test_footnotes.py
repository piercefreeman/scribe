"""Tests for the footnotes plugin."""

from pathlib import Path

import pytest

from scribe.context import PageContext
from scribe.note_plugins.config import FootnotesPluginConfig
from scribe.note_plugins.footnotes import FootnotesPlugin


class TestFootnotesPlugin:
    """Test cases for the FootnotesPlugin."""

    @pytest.fixture
    def plugin(self):
        """Create a FootnotesPlugin instance for testing."""
        config = FootnotesPluginConfig()
        return FootnotesPlugin(config)

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

    @pytest.mark.parametrize(
        "input_content,expected_content",
        [
            # Basic reordering test
            (
                "This has footnotes[^second] and[^first].\n\n"
                "[^first]: First definition\n"
                "[^second]: Second definition\n",
                "This has footnotes[^1] and[^2].\n\n"
                "[^1]: Second definition\n"
                "[^2]: First definition\n",
            ),
            # Multiple references to same footnote
            (
                "Text[^ref] and more[^ref] text.\n\n[^ref]: Single definition\n",
                "Text[^1] and more[^1] text.\n\n[^1]: Single definition\n",
            ),
            # Complex IDs with numbers and letters
            (
                "Start[^note3] middle[^a1] end[^note1].\n\n"
                "[^note1]: Note one\n"
                "[^note3]: Note three\n"
                "[^a1]: Note a1\n",
                "Start[^1] middle[^2] end[^3].\n\n"
                "[^1]: Note three\n"
                "[^2]: Note a1\n"
                "[^3]: Note one\n",
            ),
            # Mixed order definitions
            (
                "Text[^z] and[^a] and[^m].\n\n"
                "[^m]: Middle note\n"
                "[^a]: First note\n"
                "[^z]: Last note\n",
                "Text[^1] and[^2] and[^3].\n\n"
                "[^1]: Last note\n"
                "[^2]: First note\n"
                "[^3]: Middle note\n",
            ),
            # Footnotes in different parts of text
            (
                "Beginning[^start].\n\n"
                "# Section\n\n"
                "Middle[^mid] content.\n\n"
                "End[^end].\n\n"
                "[^end]: End definition\n"
                "[^start]: Start definition\n"
                "[^mid]: Middle definition\n",
                "Beginning[^1].\n\n"
                "# Section\n\n"
                "Middle[^2] content.\n\n"
                "End[^3].\n\n"
                "[^1]: Start definition\n"
                "[^2]: Middle definition\n"
                "[^3]: End definition\n",
            ),
        ],
    )
    async def test_footnote_reordering(
        self, plugin, base_context, input_content, expected_content
    ):
        """Test that footnotes are reordered correctly."""
        base_context.content = input_content
        result = await plugin.process(base_context)
        assert result.content == expected_content

    @pytest.mark.parametrize(
        "content",
        [
            # No footnotes
            "This is just regular text with no footnotes.",
            # Empty content
            "",
            # Only footnote references but no definitions
            "Text with[^missing] references[^gone].",
            # Only footnote definitions but no references
            "[^unused]: This definition is not referenced\n"
            "[^orphan]: Neither is this one\n",
            # Malformed footnotes
            "Text with [^ space] or [^] empty.",
        ],
    )
    async def test_edge_cases(self, plugin, base_context, content):
        """Test edge cases that should not crash the plugin."""
        base_context.content = content
        result = await plugin.process(base_context)
        # Should not crash and return some content
        assert isinstance(result.content, str)

    async def test_no_footnotes_unchanged(self, plugin, base_context):
        """Test that content without footnotes remains unchanged."""
        original_content = (
            "This is regular markdown content.\n\n# Header\n\nWith some **bold** text."
        )
        base_context.content = original_content
        result = await plugin.process(base_context)
        assert result.content == original_content

    async def test_preserve_content_structure(self, plugin, base_context):
        """Test that non-footnote content structure is preserved."""
        content = (
            "# Title\n\n"
            "Introduction[^intro].\n\n"
            "## Section\n\n"
            "Content[^note].\n\n"
            "- List item\n"
            "- Another item[^list]\n\n"
            "[^intro]: Introduction note\n"
            "[^note]: Section note\n"
            "[^list]: List note\n"
        )

        expected = (
            "# Title\n\n"
            "Introduction[^1].\n\n"
            "## Section\n\n"
            "Content[^2].\n\n"
            "- List item\n"
            "- Another item[^3]\n\n"
            "[^1]: Introduction note\n"
            "[^2]: Section note\n"
            "[^3]: List note\n"
        )

        base_context.content = content
        result = await plugin.process(base_context)
        assert result.content == expected

    async def test_footnotes_with_multiline_definitions(self, plugin, base_context):
        """Test footnotes with multiline definitions."""
        content = (
            "Text[^multi] here.\n\n"
            "[^multi]: This is a long footnote that spans multiple lines\n"
            "    with additional content on the next line.\n"
        )

        # Note: The current implementation captures only the first line of definitions
        # This test documents the current behavior - multiline content remains
        expected = (
            "Text[^1] here.\n\n"
            "    with additional content on the next line.\n\n"
            "[^1]: This is a long footnote that spans multiple lines\n"
        )

        base_context.content = content
        result = await plugin.process(base_context)
        assert result.content == expected

    async def test_footnotes_with_special_characters(self, plugin, base_context):
        """Test footnotes with special characters in definitions."""
        content = (
            "Text[^special].\n\n"
            "[^special]: Definition with *markdown* and [links](http://example.com)\n"
        )

        expected = (
            "Text[^1].\n\n"
            "[^1]: Definition with *markdown* and [links](http://example.com)\n"
        )

        base_context.content = content
        result = await plugin.process(base_context)
        assert result.content == expected

    async def test_missing_definitions_ignored(self, plugin, base_context):
        """Test that references without definitions are handled properly."""
        content = "Text[^exists] and[^missing].\n\n[^exists]: This definition exists\n"

        # The plugin processes all refs it finds, even if no definition exists
        # This is current behavior - could be changed to be more selective
        expected = "Text[^1] and[^2].\n\n[^1]: This definition exists\n"

        base_context.content = content
        result = await plugin.process(base_context)
        assert result.content == expected

    @pytest.mark.parametrize(
        "ending",
        [
            "",  # No newlines
            "\n",  # Single newline
            "\n\n",  # Double newline
            "\n\n\n",  # Triple newline
        ],
    )
    async def test_content_ending_preservation(self, plugin, base_context, ending):
        """Test that content ending formatting is handled properly."""
        content = f"Text[^note].{ending}[^note]: Definition"

        base_context.content = content
        result = await plugin.process(base_context)

        # Should have proper spacing before footnotes
        if ending == "":
            # Special case for no ending - content gets concatenated
            assert result.content == "Text[^1].[^1]: Definition"
        else:
            assert "[^1]: Definition\n" in result.content
            assert result.content.startswith("Text[^1].")

    async def test_large_number_of_footnotes(self, plugin, base_context):
        """Test handling of many footnotes."""
        # Create content with 20 footnotes in random order
        refs = [f"[^note{i}]" for i in range(20, 0, -1)]  # Reverse order
        defs = [f"[^note{i}]: Definition {i}" for i in range(20, 0, -1)]

        content = f"Text with footnotes: {' '.join(refs)}.\n\n{chr(10).join(defs)}\n"

        base_context.content = content
        result = await plugin.process(base_context)

        # Check that all footnotes are renumbered 1-20 in order
        for i in range(1, 21):
            assert f"[^{i}]" in result.content
            assert f"[^{i}]: Definition {21 - i}" in result.content

    async def test_plugin_preserves_other_context_fields(self, plugin, base_context):
        """Test that the plugin only modifies content, not other context fields."""
        original_content = (
            "Text[^second] and[^first].\n\n[^first]: First\n[^second]: Second"
        )
        base_context.content = original_content
        base_context.title = "Test Title"
        base_context.tags = ["test", "footnotes"]

        result = await plugin.process(base_context)

        assert result.title == "Test Title"
        assert result.tags == ["test", "footnotes"]
        assert result.source_path == base_context.source_path

        # Content should be reordered (footnotes referenced in appearance order)
        expected_content = "Text[^1] and[^2].\n\n[^1]: Second\n[^2]: First\n"
        assert result.content == expected_content
        assert result.content != original_content  # Content should be modified
