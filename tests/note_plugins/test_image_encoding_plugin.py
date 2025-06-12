"""Tests for the image encoding plugin."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from scribe.config import ScribeConfig
from scribe.context import PageContext
from scribe.note_plugins.config import ImageEncodingPluginConfig
from scribe.note_plugins.image_encoding import ImageEncodingPlugin


class TestImageEncodingPlugin:
    """Test cases for the image encoding plugin."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def sample_config(self, temp_dir: Path) -> ImageEncodingPluginConfig:
        """Create a sample configuration for testing."""
        return ImageEncodingPluginConfig(
            name="image_encoding",
            cache_dir=str(temp_dir / "cache"),
            formats=["webp", "avif"],
            quality_webp=80,
            quality_avif=65,
            max_width=1920,
            max_height=1080,
        )

    @pytest.fixture
    def site_config(self, temp_dir: Path) -> ScribeConfig:
        """Create a sample site configuration."""
        source_dir = temp_dir / "source"
        static_dir = temp_dir / "static"
        output_dir = temp_dir / "output"

        source_dir.mkdir(exist_ok=True)
        static_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)

        return ScribeConfig(
            source_dir=source_dir,
            output_dir=output_dir,
            static_path=static_dir,
        )

    @pytest.fixture
    def sample_image(self, temp_dir: Path) -> Path:
        """Create a sample test image."""
        # Create a simple test image
        img = Image.new("RGB", (1200, 800), color="red")
        image_path = temp_dir / "static" / "test_image.jpg"
        image_path.parent.mkdir(exist_ok=True)
        img.save(image_path, format="JPEG", quality=95)
        return image_path

    @pytest.fixture
    def page_context(
        self, temp_dir: Path, site_config: ScribeConfig, sample_image: Path
    ) -> PageContext:
        """Create a sample page context with image references."""
        source_file = temp_dir / "source" / "test_page.md"
        source_file.parent.mkdir(exist_ok=True)

        # Create markdown content with image references
        content = """# Test Page

This is a test page with images.

![Test Image](test_image.jpg)

Some more content here.

<img src="test_image.jpg" alt="HTML image">
"""

        source_file.write_text(content)

        output_file = temp_dir / "output" / "test_page.html"

        return PageContext(
            source_path=source_file,
            relative_path=Path("test_page.md"),
            output_path=output_file,
            raw_content=content,
            content=content,
        )

    @pytest.fixture
    def plugin(
        self, sample_config: ImageEncodingPluginConfig, site_config: ScribeConfig
    ) -> ImageEncodingPlugin:
        """Create a plugin instance with sample configuration."""
        plugin = ImageEncodingPlugin(sample_config, global_config=site_config)
        return plugin

    async def test_plugin_initialization(
        self, sample_config: ImageEncodingPluginConfig, site_config: ScribeConfig
    ) -> None:
        """Test that the plugin initializes correctly."""
        plugin = ImageEncodingPlugin(sample_config, global_config=site_config)
        assert plugin.config == sample_config
        assert plugin.name == "image_encoding"
        assert hasattr(plugin, "supports_webp")
        assert hasattr(plugin, "supports_avif")

    async def test_extract_image_references(
        self, plugin: ImageEncodingPlugin, page_context: PageContext
    ) -> None:
        """Test extracting image references from content."""
        image_refs = plugin._extract_image_references(page_context.content)
        assert len(image_refs) == 1  # Should deduplicate the same image
        assert "test_image.jpg" in image_refs

    async def test_process_page_with_images(
        self, plugin: ImageEncodingPlugin, page_context: PageContext, sample_image: Path
    ) -> None:
        """Test processing a page with image references."""
        # Process the page
        result_ctx = await plugin.process(page_context)

        # Check that plugin data was added
        assert result_ctx.image_encoding_data is not None
        assert result_ctx.image_encoding_data.processed_images is not None
        assert result_ctx.image_encoding_data.formats is not None

        # Check that images were processed
        processed_images = result_ctx.image_encoding_data.processed_images
        assert "test_image.jpg" in processed_images

        # Should include supported formats
        formats = processed_images["test_image.jpg"]
        if plugin.supports_webp:
            assert "webp" in formats
        if plugin.supports_avif:
            assert "avif" in formats

    async def test_process_page_no_images(
        self, plugin: ImageEncodingPlugin, temp_dir: Path, site_config: ScribeConfig
    ) -> None:
        """Test processing a page with no image references."""
        # Create page context without images
        source_file = temp_dir / "source" / "no_images.md"
        content = "# No Images\n\nThis page has no images."
        source_file.write_text(content)

        ctx = PageContext(
            source_path=source_file,
            relative_path=Path("no_images.md"),
            output_path=temp_dir / "output" / "no_images.html",
            raw_content=content,
            content=content,
        )

        # Process the page
        result_ctx = await plugin.process(ctx)

        # Should return the same context content but may have different slug
        assert result_ctx.raw_content == ctx.raw_content
        assert result_ctx.content == ctx.content

    async def test_resolve_image_path(
        self, plugin: ImageEncodingPlugin, page_context: PageContext, sample_image: Path
    ) -> None:
        """Test resolving image paths."""
        resolved_path = plugin._find_image_path("test_image.jpg", page_context)
        assert resolved_path == sample_image

    async def test_resolve_image_path_not_found(
        self, plugin: ImageEncodingPlugin, page_context: PageContext
    ) -> None:
        """Test resolving non-existent image paths."""
        resolved_path = plugin._find_image_path("nonexistent.jpg", page_context)
        assert resolved_path is None

    async def test_cache_key_generation(
        self, plugin: ImageEncodingPlugin, sample_image: Path, page_context: PageContext
    ) -> None:
        """Test that cache keys are generated consistently."""
        key1 = plugin._get_cache_key(sample_image, page_context)
        key2 = plugin._get_cache_key(sample_image, page_context)
        assert key1 == key2
        assert isinstance(key1, str)
        # Cache key should be based on relative path with safe characters
        assert "test_image.jpg" in key1

    async def test_extract_external_images_ignored(
        self, plugin: ImageEncodingPlugin
    ) -> None:
        """Test that external URLs are ignored."""
        content = """
        ![External](https://example.com/image.jpg)
        ![Local](local_image.jpg)
        <img src="http://example.com/image.png" alt="External HTML">
        <img src="local.png" alt="Local HTML">
        """

        image_refs = plugin._extract_image_references(content)
        assert len(image_refs) == 2
        assert "local_image.jpg" in image_refs
        assert "local.png" in image_refs
        assert "https://example.com/image.jpg" not in image_refs
        assert "http://example.com/image.png" not in image_refs

    async def test_process_with_cache(
        self,
        plugin: ImageEncodingPlugin,
        page_context: PageContext,
        sample_image: Path,
        temp_dir: Path,
    ) -> None:
        """Test that caching works correctly."""
        # Process first time
        await plugin.process(page_context)

        # Check that cache directory was created
        cache_dir = temp_dir / "cache"
        assert cache_dir.exists()

        # Get cache files
        cache_files = list(cache_dir.rglob("*"))
        initial_cache_count = len([f for f in cache_files if f.is_file()])

        # Process again - should use cache
        await plugin.process(page_context)

        # Cache file count should be the same (files reused)
        new_cache_files = list(cache_dir.rglob("*"))
        new_cache_count = len([f for f in new_cache_files if f.is_file()])
        assert new_cache_count == initial_cache_count

    async def test_cache_validation(
        self,
        plugin: ImageEncodingPlugin,
        page_context: PageContext,
        sample_image: Path,
        temp_dir: Path,
    ) -> None:
        """Test that cache validation works correctly."""
        cache_key = plugin._get_cache_key(sample_image, page_context)
        cache_dir = temp_dir / "cache" / cache_key

        # Initially no cache
        assert not plugin._is_cache_valid(cache_dir, sample_image)

        # Create cache directory with a file
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "test.webp"
        cache_file.write_text("fake image data")

        # Cache should be valid (newer than source)
        assert plugin._is_cache_valid(cache_dir, sample_image)

        # If we modify the source image, cache should be invalid
        sample_image.touch()  # Update modification time
        assert not plugin._is_cache_valid(cache_dir, sample_image)

    async def test_image_path_rewriting(
        self,
        plugin: ImageEncodingPlugin,
        temp_dir: Path,
        site_config: ScribeConfig,
        sample_image: Path,
    ) -> None:
        """Test that image paths are rewritten in content after processing."""
        # Create a fresh page context for this test
        source_file = temp_dir / "source" / "rewrite_test.md"
        source_file.parent.mkdir(exist_ok=True)

        # Create content with original jpg references
        original_content = """# Test Page

This is a test page with images.

![Test Image](test_image.jpg)

Some more content here.

<img src="test_image.jpg" alt="HTML image">
"""

        source_file.write_text(original_content)

        ctx = PageContext(
            source_path=source_file,
            relative_path=Path("rewrite_test.md"),
            output_path=temp_dir / "output" / "rewrite_test.html",
            raw_content=original_content,
            content=original_content,
        )

        # Process the page which should rewrite image paths
        result_ctx = await plugin.process(ctx)

        # Check that content was modified to use converted format
        new_content = result_ctx.content

        # Original content should have .jpg references
        assert "test_image.jpg" in original_content

        # New content should have converted format references with absolute
        # paths (assuming webp is supported)
        if plugin.supports_webp:
            assert "/test_image.webp" in new_content
            assert "test_image.jpg" not in new_content

            # Check both markdown and HTML image formats are rewritten with
            # absolute paths
            assert "![Test Image](/test_image.webp)" in new_content
            assert '<img src="/test_image.webp"' in new_content
        elif plugin.supports_avif:
            assert "/test_image.avif" in new_content
            assert "test_image.jpg" not in new_content

            # Check both markdown and HTML image formats are rewritten with
            # absolute paths
            assert "![Test Image](/test_image.avif)" in new_content
            assert '<img src="/test_image.avif"' in new_content

    async def test_path_rewriting_with_subdirectories(
        self, plugin: ImageEncodingPlugin, temp_dir: Path, site_config: ScribeConfig
    ) -> None:
        """Test that image path rewriting works with subdirectories."""
        # Create image in subdirectory
        subdir = temp_dir / "static" / "images"
        subdir.mkdir(parents=True, exist_ok=True)

        img = Image.new("RGB", (100, 100), color="blue")
        image_path = subdir / "nested_image.png"
        img.save(image_path, format="PNG")

        # Create page context with subdirectory image reference
        source_file = temp_dir / "source" / "test_page.md"
        content = """# Test Page

![Nested Image](images/nested_image.png)

<img src="images/nested_image.png" alt="HTML nested image">
"""

        source_file.write_text(content)

        ctx = PageContext(
            source_path=source_file,
            relative_path=Path("test_page.md"),
            output_path=temp_dir / "output" / "test_page.html",
            raw_content=content,
            content=content,
        )

        # Process the page
        result_ctx = await plugin.process(ctx)

        # Check that subdirectory paths are rewritten correctly with absolute paths
        if plugin.supports_webp:
            assert "/images/nested_image.webp" in result_ctx.content
            assert "images/nested_image.png" not in result_ctx.content
