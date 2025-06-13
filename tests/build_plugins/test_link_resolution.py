"""Tests for the LinkResolutionBuildPlugin."""

from pathlib import Path

import pytest

from scribe.build_plugins.config import LinkResolutionBuildPluginConfig
from scribe.build_plugins.link_resolution import (
    HtmlLinkProcessor,
    LinkResolutionBuildPlugin,
    LinkResolver,
    PageLink,
    PageSlugMapBuilder,
    UrlBuilder,
)
from scribe.config import NoteTemplate, ScribeConfig, TemplateConfig
from scribe.context import PageContext


class TestPageLink:
    """Test the PageLink domain object."""

    def test_external_link_detection(self):
        """Test external link detection."""
        external_links = [
            "https://example.com",
            "http://example.com",
            "mailto:test@example.com",
            "ftp://example.com",
            "//example.com",
        ]

        for url in external_links:
            link = PageLink(url=url)
            assert link.is_external(), f"Expected {url} to be external"
            assert not link.should_resolve(), f"Expected {url} not to be resolved"

    def test_anchor_link_detection(self):
        """Test anchor link detection."""
        link = PageLink(url="#header")
        assert link.is_anchor()
        assert not link.should_resolve()

    def test_internal_link_detection(self):
        """Test internal link detection."""
        internal_links = [
            "local-page",
            "./relative-page",
            "../parent-page",
            "local-page.md",
        ]

        for url in internal_links:
            link = PageLink(url=url)
            assert not link.is_external(), f"Expected {url} not to be external"
            assert not link.is_anchor(), f"Expected {url} not to be anchor"
            assert link.should_resolve(), f"Expected {url} to be resolved"


class TestUrlBuilder:
    """Test the UrlBuilder functionality."""

    @pytest.fixture
    def site_config_with_templates(self, tmp_path):
        """Create a site config with note templates."""
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
    def site_config_no_templates(self, tmp_path):
        """Create a site config without templates."""
        return ScribeConfig(
            source_dir=tmp_path / "content",
            output_dir=tmp_path / "output",
        )

    @pytest.fixture
    def sample_context(self, tmp_path):
        """Create a sample page context."""
        return PageContext(
            source_path=tmp_path / "content" / "first-note.md",
            relative_path=Path("first-note.md"),
            output_path=tmp_path / "output" / "notes" / "first-note" / "index.html",
            raw_content="# First Note\n\nContent.",
            content="<h1>First Note</h1>\n<p>Content.</p>",
            title="First Note",
            slug="first-note",
        )

    def test_url_building_with_templates(
        self, site_config_with_templates, sample_context
    ):
        """Test URL building when templates are configured."""
        url_builder = UrlBuilder()
        url = url_builder.build_url(sample_context, site_config_with_templates)
        assert url == "/notes/first-note/"

    def test_url_building_no_templates(self, site_config_no_templates, sample_context):
        """Test URL building when no templates are configured."""
        url_builder = UrlBuilder()
        url = url_builder.build_url(sample_context, site_config_no_templates)
        assert url == "/first-note/"


class TestLinkResolver:
    """Test the LinkResolver functionality."""

    @pytest.fixture
    def slug_map(self):
        """Create a test slug map."""
        return {
            "first-note": "/notes/first-note/",
            "second-note": "/notes/second-note/",
            "First Note": "/notes/first-note/",
        }

    @pytest.fixture
    def sample_context(self, tmp_path):
        """Create a sample context for testing."""
        return PageContext(
            source_path=tmp_path / "content" / "test.md",
            relative_path=Path("test.md"),
            output_path=tmp_path / "output" / "test.html",
            raw_content="",
            slug="test",
        )

    def test_resolve_direct_match(self, slug_map, sample_context):
        """Test direct link resolution."""
        resolver = LinkResolver(slug_map)

        link = PageLink(url="first-note")
        result = resolver.resolve(link, sample_context)
        assert result == "/notes/first-note/"

    def test_resolve_with_md_extension(self, slug_map, sample_context):
        """Test resolution of links with .md extension."""
        resolver = LinkResolver(slug_map)

        link = PageLink(url="first-note.md")
        result = resolver.resolve(link, sample_context)
        assert result == "/notes/first-note/"

    def test_resolve_no_match(self, slug_map, sample_context):
        """Test resolution when no match is found."""
        resolver = LinkResolver(slug_map)

        link = PageLink(url="non-existent")
        result = resolver.resolve(link, sample_context)
        assert result == "non-existent.md"

    def test_resolve_external_link_unchanged(self, slug_map, sample_context):
        """Test that external links are not resolved."""
        resolver = LinkResolver(slug_map)

        link = PageLink(url="https://example.com")
        result = resolver.resolve(link, sample_context)
        assert result == "https://example.com"

    def test_resolve_anchor_link_unchanged(self, slug_map, sample_context):
        """Test that anchor links are not resolved."""
        resolver = LinkResolver(slug_map)

        link = PageLink(url="#header")
        result = resolver.resolve(link, sample_context)
        assert result == "#header"

    def test_resolve_md_file_not_found_raises_exception(self):
        """Test that missing .md files raise FileNotFoundError."""
        slug_map = {"existing.md": "/existing/"}
        resolver = LinkResolver(slug_map)

        # Create a temporary directory structure for testing
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_file = temp_path / "test.md"
            source_file.touch()  # Create the source file

            # Create a context with the source file
            ctx = PageContext(
                source_path=source_file,
                relative_path=Path("test.md"),
                output_path=temp_path / "output" / "test.html",
                content="",
                raw_content="",
                slug="test",
            )

            # Test that non-existent .md file raises exception
            link = PageLink(url="nonexistent.md")

            with pytest.raises(FileNotFoundError, match="Markdown file not found"):
                resolver.resolve(link, ctx)


class TestHtmlLinkProcessor:
    """Test the HtmlLinkProcessor."""

    @pytest.fixture
    def processor(self):
        """Create an HTML link processor with a mock resolver."""
        slug_map = {"target": "/notes/target/"}
        resolver = LinkResolver(slug_map)
        return HtmlLinkProcessor(resolver)

    @pytest.fixture
    def sample_context(self, tmp_path):
        """Create a sample context."""
        return PageContext(
            source_path=tmp_path / "content" / "test.md",
            relative_path=Path("test.md"),
            output_path=tmp_path / "output" / "test.html",
            raw_content="",
            slug="test",
        )

    def test_process_html_link_resolution(self, processor, sample_context):
        """Test that HTML links are resolved correctly."""
        content = '<p>This is a <a href="target.md">link to target</a> page.</p>'
        result = processor.process(content, sample_context)
        assert "target.md" not in result
        assert "/notes/target/" in result

    def test_process_external_links_unchanged(self, processor, sample_context):
        """Test that external HTML links are unchanged."""
        content = '<p>This is an <a href="https://example.com">external link</a>.</p>'
        result = processor.process(content, sample_context)
        assert "https://example.com" in result

    def test_process_anchor_links_unchanged(self, processor, sample_context):
        """Test that anchor HTML links are unchanged."""
        content = '<p>Jump to <a href="#header">section</a> below.</p>'
        result = processor.process(content, sample_context)
        assert "#header" in result


class TestPageSlugMapBuilder:
    """Test the PageSlugMapBuilder."""

    @pytest.fixture
    def url_builder(self):
        """Create a URL builder."""
        return UrlBuilder()

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
        """Create sample page contexts."""
        contexts = []

        ctx1 = PageContext(
            source_path=tmp_path / "content" / "first-note.md",
            relative_path=Path("first-note.md"),
            output_path=tmp_path / "output" / "notes" / "first-note" / "index.html",
            raw_content="# First Note\n\nContent.",
            title="First Note",
            slug="first-note",
        )
        contexts.append(ctx1)

        ctx2 = PageContext(
            source_path=tmp_path / "content" / "second-note.md",
            relative_path=Path("second-note.md"),
            output_path=tmp_path / "output" / "notes" / "second-note" / "index.html",
            raw_content="# Second Note\n\nContent.",
            title="Second Note",
            slug="second-note",
        )
        contexts.append(ctx2)

        return contexts

    def test_build_slug_map(self, url_builder, sample_contexts, site_config):
        """Test building a slug map from contexts."""
        builder = PageSlugMapBuilder(url_builder)
        slug_map = builder.build(sample_contexts, site_config)

        # Should map various identifiers to URLs
        assert slug_map["first-note"] == "/notes/first-note/"
        assert slug_map["First Note"] == "/notes/first-note/"
        assert slug_map["second-note"] == "/notes/second-note/"
        assert slug_map["Second Note"] == "/notes/second-note/"


class TestLinkResolutionBuildPlugin:
    """Test the main LinkResolutionBuildPlugin functionality."""

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

        # Create second note with HTML links
        # (not markdown, since that's already converted)
        note2_path = tmp_path / "content" / "second-note.md"
        note2_path.write_text("# Second Note\n\nThis references the first note.")

        ctx2 = PageContext(
            source_path=note2_path,
            relative_path=Path("second-note.md"),
            output_path=tmp_path / "output" / "notes" / "second-note" / "index.html",
            raw_content="# Second Note\n\nThis references the first note.",
            content=(
                "<h1>Second Note</h1>\n<p>This references "
                '<a href="first-note.md">the first note</a>.</p>'
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

    async def test_after_notes_processes_contexts(
        self, plugin, site_config, sample_contexts, tmp_path
    ):
        """Test that after_notes processes all contexts."""
        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", sample_contexts
        )

        # Should return the same number of contexts
        assert len(result_contexts) == 2
        assert result_contexts[0].slug == "first-note"
        assert result_contexts[1].slug == "second-note"

    async def test_html_link_resolution(
        self, plugin, site_config, sample_contexts, tmp_path
    ):
        """Test that HTML links are resolved correctly."""
        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", sample_contexts
        )

        # The second note should have its HTML link resolved
        second_note = result_contexts[1]
        assert "/notes/first-note/" in second_note.content
        assert "first-note.md" not in second_note.content

    async def test_external_links_unchanged(self, plugin, site_config, tmp_path):
        """Test that external links are not modified."""
        ctx = PageContext(
            source_path=tmp_path / "content" / "external.md",
            relative_path=Path("external.md"),
            output_path=tmp_path / "output" / "external.html",
            raw_content="# External\n\nLink to Google.",
            content='<h1>External</h1>\n<p>Link to <a href="https://google.com">Google</a>.</p>',
            title="External",
            slug="external",
        )

        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", [ctx]
        )

        # External links should be unchanged
        assert "https://google.com" in result_contexts[0].content

    async def test_anchor_links_unchanged(self, plugin, site_config, tmp_path):
        """Test that anchor links are not modified."""
        ctx = PageContext(
            source_path=tmp_path / "content" / "anchors.md",
            relative_path=Path("anchors.md"),
            output_path=tmp_path / "output" / "anchors.html",
            raw_content="# Anchors\n\nJump to section.",
            content='<h1>Anchors</h1>\n<p>Jump to <a href="#header">section</a>.</p>',
            title="Anchors",
            slug="anchors",
        )

        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", [ctx]
        )

        # Anchor links should be unchanged
        assert "#header" in result_contexts[0].content

    async def test_mixed_link_types(self, plugin, site_config, tmp_path):
        """Test processing content with mixed link types."""
        # Create a context with different types of links
        ctx = PageContext(
            source_path=tmp_path / "content" / "mixed.md",
            relative_path=Path("mixed.md"),
            output_path=tmp_path / "output" / "mixed.html",
            raw_content="# Mixed Links\n\nVarious link types.",
            content=(
                "<h1>Mixed Links</h1>\n"
                '<p>Internal: <a href="target.md">target</a></p>\n'
                '<p>External: <a href="https://example.com">example</a></p>\n'
                '<p>Anchor: <a href="#section">section</a></p>'
            ),
            title="Mixed Links",
            slug="mixed",
        )

        # Create target context
        target_ctx = PageContext(
            source_path=tmp_path / "content" / "target.md",
            relative_path=Path("target.md"),
            output_path=tmp_path / "output" / "target.html",
            raw_content="# Target\n\nContent.",
            title="Target",
            slug="target",
        )

        result_contexts = await plugin.after_notes(
            site_config, tmp_path / "output", [ctx, target_ctx]
        )

        result_content = result_contexts[0].content

        # Internal links should be resolved
        assert "/notes/target/" in result_content
        assert "target.md" not in result_content

        # External and anchor links should be unchanged
        assert "https://example.com" in result_content
        assert "#section" in result_content
