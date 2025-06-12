"""Tests for the link resolution plugin."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from scribe.config import ScribeConfig
from scribe.context import PageContext
from scribe.note_plugins.config import LinkResolutionPluginConfig
from scribe.note_plugins.link_resolution import LinkResolutionPlugin


class TestLinkResolutionPlugin:
    """Test cases for the LinkResolutionPlugin."""

    @pytest.fixture
    def global_config(self, tmp_path):
        """Create a global config for testing."""
        source_dir = tmp_path / "content"
        source_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        return ScribeConfig(
            source_dir=source_dir,
            output_dir=output_dir,
        )

    @pytest.fixture
    def plugin(self, global_config):
        """Create a LinkResolutionPlugin instance for testing."""
        config = LinkResolutionPluginConfig()
        return LinkResolutionPlugin(config, global_config)

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

    def test_plugin_initialization(self, plugin, global_config):
        """Test that the plugin initializes correctly."""
        assert plugin.name == "link_resolution"
        assert plugin.global_config == global_config
        assert plugin._page_slug_map == {}
        assert not plugin._page_slug_map_initialized

    def test_external_link_detection(self, plugin):
        """Test that external links are correctly identified."""
        assert plugin._is_external_link("https://example.com")
        assert plugin._is_external_link("http://example.com")
        assert plugin._is_external_link("mailto:test@example.com")
        assert plugin._is_external_link("ftp://example.com")
        assert plugin._is_external_link("//example.com")

        assert not plugin._is_external_link("internal-page")
        assert not plugin._is_external_link("./relative-page")
        assert not plugin._is_external_link("../parent-page")
        assert not plugin._is_external_link("/absolute-page")

    def test_markdown_link_pattern(self, plugin):
        """Test that the markdown link pattern correctly matches links."""
        content = "Here is a [link](page.md) and another [link](https://example.com)."
        matches = list(plugin.markdown_link_pattern.finditer(content))

        assert len(matches) == 2
        assert matches[0].group(1) == "link"
        assert matches[0].group(2) == "page.md"
        assert matches[1].group(1) == "link"
        assert matches[1].group(2) == "https://example.com"

    def test_build_page_slug_map_empty_directory(self, plugin, global_config):
        """Test building slug map with empty source directory."""
        plugin._build_page_slug_map()

        assert plugin._page_slug_map_initialized
        assert plugin._page_slug_map == {}

    def test_build_page_slug_map_with_files(self, plugin, global_config):
        """Test building slug map with markdown files."""
        # Create test files
        file1 = global_config.source_dir / "page-one.md"
        file1.write_text("# Page One\n\nContent here.")

        file2 = global_config.source_dir / "page-two.md"
        file2.write_text("# Page Two\n\nMore content.")

        plugin._build_page_slug_map()

        assert plugin._page_slug_map_initialized
        assert len(plugin._page_slug_map) > 0

        # Should map filename to slug
        assert "page-one" in plugin._page_slug_map
        assert "page-two" in plugin._page_slug_map

        # Should map title to slug
        assert "Page One" in plugin._page_slug_map
        assert "Page Two" in plugin._page_slug_map

    def test_create_temp_context(self, plugin, global_config):
        """Test creating temporary context for slug extraction."""
        # Create a test file
        test_file = global_config.source_dir / "test-page.md"
        test_file.write_text("# Test Page\n\nContent here.")

        relative_path = Path("test-page.md")
        temp_ctx = plugin._create_temp_context(test_file, relative_path)

        assert temp_ctx.source_path == test_file
        assert temp_ctx.relative_path == relative_path
        assert temp_ctx.title == "Test Page"
        assert temp_ctx.slug == "test-page"

    def test_generate_url_from_slug_default(self, plugin):
        """Test URL generation with default configuration."""
        url = plugin._generate_url_from_slug("my-page")
        assert url == "/my-page/"

    def test_generate_url_from_slug_with_template(self, plugin, global_config):
        """Test URL generation with template configuration."""
        from scribe.config import NoteTemplate, TemplateConfig

        template = NoteTemplate(
            template_path="note.html", url_pattern="/posts/{slug}/", predicates=[]
        )

        global_config.templates = TemplateConfig(
            template_path=Path("templates"),
            note_templates=[template],
            base_templates=[],
        )

        url = plugin._generate_url_from_slug("my-page")
        assert url == "/posts/my-page/"

    async def test_process_no_links(self, plugin, base_context):
        """Test processing content with no links."""
        base_context.content = "# Title\n\nThis is content without links."

        result = await plugin.process(base_context)

        assert result.content == "# Title\n\nThis is content without links."

    async def test_process_external_links_unchanged(self, plugin, base_context):
        """Test that external links are not modified."""
        content = (
            "Check out [this site](https://example.com) and "
            "[email me](mailto:test@example.com)."
        )
        base_context.content = content

        result = await plugin.process(base_context)

        assert result.content == content

    async def test_process_anchor_links_unchanged(self, plugin, base_context):
        """Test that anchor links are not modified."""
        content = "Go to [section](#section) or [top](#top)."
        base_context.content = content

        result = await plugin.process(base_context)

        assert result.content == content

    async def test_process_resolve_page_links(
        self, plugin, base_context, global_config
    ):
        """Test resolving page links to actual slugs."""
        # Create target files
        target_file = global_config.source_dir / "target-page.md"
        target_file.write_text("# Target Page\n\nContent here.")

        # Set up content with links
        content = "Check out [this page](target-page.md) and [another](target-page)."
        base_context.content = content

        result = await plugin.process(base_context)

        # Links should be resolved to slug-based URLs
        assert "/target-page/" in result.content
        assert "target-page.md" not in result.content

    async def test_process_unresolvable_links(self, plugin, base_context):
        """Test that unresolvable links are left mostly unchanged."""
        content = "Check out [this page](nonexistent-page.md)."
        base_context.content = content

        result = await plugin.process(base_context)

        # Should restore .md extension for unresolvable links
        assert "nonexistent-page.md" in result.content

    def test_resolve_page_link_direct_match(self, plugin):
        """Test resolving a page link with direct slug map match."""
        plugin._page_slug_map = {"target-page": "target-page-slug"}

        result = plugin._resolve_page_link("target-page.md", Mock())

        assert result == "/target-page-slug/"

    def test_resolve_page_link_no_match(self, plugin):
        """Test resolving a page link with no slug map match."""
        plugin._page_slug_map = {}

        result = plugin._resolve_page_link("nonexistent.md", Mock())

        assert result == "nonexistent.md"

    async def test_process_integration(self, plugin, base_context, global_config):
        """Test full integration with multiple types of links."""
        # Create target files
        target1 = global_config.source_dir / "page-one.md"
        target1.write_text("# Page One\n\nContent here.")

        target2 = global_config.source_dir / "page-two.md"
        target2.write_text("# Page Two\n\nMore content.")

        # Set up content with various link types
        content = """# Main Page

Here are some links:
- [Internal page](page-one.md)
- [Another internal](page-two)
- [External site](https://example.com)
- [Email link](mailto:test@example.com)
- [Anchor link](#section)
- [Nonexistent page](missing-page.md)
"""
        base_context.content = content

        result = await plugin.process(base_context)

        # Internal links should be resolved
        assert "/page-one/" in result.content
        assert "/page-two/" in result.content

        # External links should be unchanged
        assert "https://example.com" in result.content
        assert "mailto:test@example.com" in result.content

        # Anchor links should be unchanged
        assert "#section" in result.content

        # Nonexistent links should have .md extension restored
        assert "missing-page.md" in result.content

    def test_try_relative_path_resolution(self, plugin, global_config):
        """Test relative path resolution."""
        # Create directory structure
        subdir = global_config.source_dir / "posts"
        subdir.mkdir()

        target_file = subdir / "other-post.md"
        target_file.write_text("# Other Post\n\nContent here.")

        # Build the slug map
        plugin._build_page_slug_map()

        # Create context for a file in the same directory
        ctx = PageContext(
            source_path=subdir / "current-post.md",
            relative_path=Path("posts/current-post.md"),
            output_path=Path("posts/current-post.html"),
            raw_content="",
            content="",
        )

        # Test relative path resolution
        result = plugin._try_relative_path_resolution("./other-post", ctx)

        assert result == "/other-post/"
