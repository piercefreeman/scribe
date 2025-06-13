"""Tests for the LinkResolutionBuildPlugin."""

from pathlib import Path

import pytest

from scribe.build_plugins.config import LinkResolutionBuildPluginConfig
from scribe.build_plugins.link_resolution import LinkResolutionBuildPlugin
from scribe.config import NoteTemplate, ScribeConfig, TemplateConfig
from scribe.context import PageContext


class TestLinkResolutionBuildPlugin:
    """Test the LinkResolutionBuildPlugin functionality."""

    @pytest.fixture
    def plugin_config(self):
        """Create a test plugin configuration."""
        return LinkResolutionBuildPluginConfig()

    @pytest.fixture
    def plugin(self, plugin_config):
        """Create a plugin instance."""
        return LinkResolutionBuildPlugin(plugin_config)

    @pytest.fixture
    def site_config(self, tmp_path):
        """Create a test site configuration."""
        return ScribeConfig(
            source_dir=tmp_path / "content",
            output_dir=tmp_path / "output",
            templates=TemplateConfig(
                template_path=tmp_path / "templates",
                note_templates=[
                    NoteTemplate(
                        template_path="note.html",
                        url_pattern="/notes/{slug}/",
                        predicates=[],
                    )
                ],
            ),
        )

    @pytest.fixture
    def sample_contexts(self, tmp_path):
        """Create sample page contexts for testing."""
        contexts = []

        # Create first note
        note1_path = tmp_path / "content" / "first-note.md"
        note1_path.parent.mkdir(parents=True, exist_ok=True)
        note1_path.write_text("# First Note\n\nThis is the first note.")

        ctx1 = PageContext(
            source_path=note1_path,
            relative_path=Path("first-note.md"),
            output_path=tmp_path / "output" / "notes" / "first-note" / "index.html",
            raw_content="# First Note\n\nThis is the first note.",
            content="<h1>First Note</h1>\n<p>This is the first note.</p>",
            title="First Note",
            slug="first-note",
        )
        contexts.append(ctx1)

        # Create second note
        note2_path = tmp_path / "content" / "second-note.md"
        note2_path.write_text(
            "# Second Note\n\nThis references [First Note](first-note.md)."
        )

        ctx2 = PageContext(
            source_path=note2_path,
            relative_path=Path("second-note.md"),
            output_path=tmp_path / "output" / "notes" / "second-note" / "index.html",
            raw_content="# Second Note\n\nThis references [First Note](first-note.md).",
            content=(
                "<h1>Second Note</h1>\n<p>This references "
                '<a href="first-note.md">First Note</a>.</p>'
            ),
            title="Second Note",
            slug="second-note",
        )
        contexts.append(ctx2)

        return contexts

    async def test_plugin_initialization(self, plugin_config):
        """Test that the plugin initializes correctly."""
        plugin = LinkResolutionBuildPlugin(plugin_config)
        assert plugin.name == "link_resolution"
        assert plugin.markdown_link_pattern is not None

    async def test_after_notes_builds_slug_map(
        self, plugin, site_config, sample_contexts, tmp_path
    ):
        """Test that after_notes builds the slug map correctly."""
        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", sample_contexts
        )

        # Should return the same contexts (possibly modified)
        assert len(result_contexts) == 2
        assert result_contexts[0].slug == "first-note"
        assert result_contexts[1].slug == "second-note"

    async def test_link_resolution_in_content(
        self, plugin, site_config, sample_contexts, tmp_path
    ):
        """Test that links are resolved correctly in content."""
        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", sample_contexts
        )

        # The second note should have its link resolved
        second_note = result_contexts[1]
        assert "/notes/first-note/" in second_note.content
        assert "first-note.md" not in second_note.content

    async def test_external_links_unchanged(self, plugin, site_config, tmp_path):
        """Test that external links are not modified."""
        ctx = PageContext(
            source_path=tmp_path / "content" / "external.md",
            relative_path=Path("external.md"),
            output_path=tmp_path / "output" / "external.html",
            raw_content="# External\n\nLink to [Google](https://google.com).",
            content='<h1>External</h1>\n<p>Link to <a href="https://google.com">Google</a>.</p>',
            title="External",
            slug="external",
        )

        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", [ctx]
        )

        # External link should be unchanged
        assert "https://google.com" in result_contexts[0].content

    async def test_anchor_links_unchanged(self, plugin, site_config, tmp_path):
        """Test that anchor links are not modified."""
        ctx = PageContext(
            source_path=tmp_path / "content" / "anchors.md",
            relative_path=Path("anchors.md"),
            output_path=tmp_path / "output" / "anchors.html",
            raw_content="# Anchors\n\nJump to [section](#header).",
            content='<h1>Anchors</h1>\n<p>Jump to <a href="#header">section</a>.</p>',
            title="Anchors",
            slug="anchors",
        )

        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", [ctx]
        )

        # Anchor link should be unchanged
        assert "#header" in result_contexts[0].content

    async def test_build_page_slug_map(self, plugin, sample_contexts, site_config):
        """Test the _build_page_slug_map method."""
        slug_map = plugin._build_page_slug_map(sample_contexts, site_config)

        # Should map filename, relative path, and title to URLs
        assert "first-note" in slug_map
        assert "First Note" in slug_map
        assert slug_map["first-note"] == "/notes/first-note/"
        assert slug_map["First Note"] == "/notes/first-note/"

    async def test_get_final_url_for_context(
        self, plugin, sample_contexts, site_config
    ):
        """Test the _get_final_url_for_context method."""
        ctx = sample_contexts[0]
        final_url = plugin._get_final_url_for_context(ctx, site_config)
        assert final_url == "/notes/first-note/"

    async def test_get_final_url_for_context_no_templates(
        self, plugin, sample_contexts, tmp_path
    ):
        """Test URL generation when no templates are configured."""
        site_config_no_templates = ScribeConfig(
            source_dir=tmp_path / "content",
            output_dir=tmp_path / "output",
        )

        ctx = sample_contexts[0]
        final_url = plugin._get_final_url_for_context(ctx, site_config_no_templates)
        assert final_url == "/first-note/"

    async def test_resolve_page_link_direct_match(self, plugin):
        """Test direct link resolution."""
        page_slug_map = {
            "first-note": "/notes/first-note/",
            "second-note": "/notes/second-note/",
        }

        # Create a dummy context (not used in this method)
        ctx = PageContext(
            source_path=Path("dummy.md"),
            relative_path=Path("dummy.md"),
            output_path=Path("dummy.html"),
            raw_content="",
        )

        result = plugin._resolve_page_link("first-note", ctx, page_slug_map)
        assert result == "/notes/first-note/"

    async def test_resolve_page_link_with_md_extension(self, plugin):
        """Test link resolution when the link has .md extension."""
        page_slug_map = {
            "first-note": "/notes/first-note/",
        }

        ctx = PageContext(
            source_path=Path("dummy.md"),
            relative_path=Path("dummy.md"),
            output_path=Path("dummy.html"),
            raw_content="",
        )

        result = plugin._resolve_page_link("first-note.md", ctx, page_slug_map)
        assert result == "/notes/first-note/"

    async def test_resolve_page_link_no_match(self, plugin):
        """Test link resolution when no match is found."""
        page_slug_map = {
            "existing-note": "/notes/existing-note/",
        }

        ctx = PageContext(
            source_path=Path("dummy.md"),
            relative_path=Path("dummy.md"),
            output_path=Path("dummy.html"),
            raw_content="",
        )

        result = plugin._resolve_page_link("non-existent", ctx, page_slug_map)
        assert result == "non-existent.md"  # Should add .md back

    async def test_is_external_link(self, plugin):
        """Test external link detection."""
        assert plugin._is_external_link("https://example.com")
        assert plugin._is_external_link("http://example.com")
        assert plugin._is_external_link("mailto:test@example.com")
        assert plugin._is_external_link("ftp://example.com")
        assert plugin._is_external_link("//example.com")

        assert not plugin._is_external_link("local-page")
        assert not plugin._is_external_link("./relative-page")
        assert not plugin._is_external_link("../parent-page")
        assert not plugin._is_external_link("#anchor")
