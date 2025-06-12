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
        self,
        sample_config: ImageEncodingPluginConfig,
        site_config: ScribeConfig,
        temp_dir: Path,
    ) -> None:
        """Test that path rewriting handles subdirectories correctly."""
        # Create subdirectory structure
        sub_dir = temp_dir / "static" / "images" / "gallery"
        sub_dir.mkdir(parents=True, exist_ok=True)

        # Create test image in subdirectory
        img = Image.new("RGB", (100, 100), color="blue")
        image_path = sub_dir / "photo.jpg"
        img.save(image_path, format="JPEG")

        # Create page context with content referencing subdirectory image
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content="![Gallery photo](images/gallery/photo.jpg)",
            content="![Gallery photo](images/gallery/photo.jpg)",
        )

        plugin = ImageEncodingPlugin(sample_config, site_config)
        result = await plugin.process(ctx)

        # Should rewrite to use subdirectory in output path
        assert (
            "/images/gallery/photo.webp" in result.content
            or "/images/gallery/photo.avif" in result.content
        )

    async def test_featured_photos_processing(
        self,
        sample_config: ImageEncodingPluginConfig,
        site_config: ScribeConfig,
        temp_dir: Path,
    ) -> None:
        """Test that featured_photos are processed and updated correctly."""
        # Create test images
        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="blue")

        image1_path = temp_dir / "static" / "featured1.jpg"
        image2_path = temp_dir / "static" / "featured2.jpg"

        img1.save(image1_path, format="JPEG")
        img2.save(image2_path, format="JPEG")

        # Create page context with featured_photos
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content="Some content without images in text",
            content="Some content without images in text",
            featured_photos=["featured1.jpg", "featured2.jpg"],
        )

        plugin = ImageEncodingPlugin(sample_config, site_config)
        result = await plugin.process(ctx)

        # Should process featured_photos and update them to converted paths
        assert len(result.featured_photos) == 2

        # Featured photos should be updated to point to converted images
        converted_photo1 = result.featured_photos[0]
        converted_photo2 = result.featured_photos[1]

        # Should have .webp or .avif extension
        # (depending on which format is first in config)
        assert converted_photo1.endswith((".webp", ".avif"))
        assert converted_photo2.endswith((".webp", ".avif"))

        # Should start with / for absolute path
        assert converted_photo1.startswith("/")
        assert converted_photo2.startswith("/")

        # Should contain the base names
        assert "featured1" in converted_photo1
        assert "featured2" in converted_photo2

    async def test_featured_photos_with_content_images(
        self,
        sample_config: ImageEncodingPluginConfig,
        site_config: ScribeConfig,
        temp_dir: Path,
    ) -> None:
        """Test processing both featured_photos and content images together."""
        # Create test images
        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="blue")
        img3 = Image.new("RGB", (100, 100), color="green")

        image1_path = temp_dir / "static" / "featured.jpg"
        image2_path = temp_dir / "static" / "content.jpg"
        image3_path = (
            temp_dir / "static" / "both.jpg"
        )  # Used in both featured and content

        img1.save(image1_path, format="JPEG")
        img2.save(image2_path, format="JPEG")
        img3.save(image3_path, format="JPEG")

        # Create page context with both featured_photos and content images
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content="![Content image](content.jpg) ![Shared image](both.jpg)",
            content="![Content image](content.jpg) ![Shared image](both.jpg)",
            featured_photos=["featured.jpg", "both.jpg"],
        )

        plugin = ImageEncodingPlugin(sample_config, site_config)
        result = await plugin.process(ctx)

        # Should process all unique images
        assert result.image_encoding_data is not None
        processed_images = result.image_encoding_data.processed_images

        # Should have processed 3 unique images
        assert len(processed_images) == 3
        assert "featured.jpg" in processed_images
        assert "content.jpg" in processed_images
        assert "both.jpg" in processed_images

        # Should update featured_photos
        assert len(result.featured_photos) == 2
        assert all(
            photo.endswith((".webp", ".avif")) for photo in result.featured_photos
        )

        # Should update content
        assert "content.webp" in result.content or "content.avif" in result.content
        assert "both.webp" in result.content or "both.avif" in result.content
