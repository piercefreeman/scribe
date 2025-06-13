"""Tests for the image encoding plugin."""

import tempfile
from pathlib import Path

import pytest
import pyvips

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
            formats=["webp"],
            quality_webp=80,
            max_width=1920,
            max_height=1080,
            generate_responsive=True,
            responsive_sizes=[400, 800, 1200],
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
        # Create a simple test image as PNG to avoid JPEG compatibility issues
        img = pyvips.Image.black(1200, 800, bands=3).ifthenelse([255, 0, 0], [0, 0, 0])
        image_path = temp_dir / "static" / "test_image.png"
        image_path.parent.mkdir(exist_ok=True)
        img.write_to_file(str(image_path))
        return image_path

    @pytest.fixture
    def page_context(
        self, temp_dir: Path, site_config: ScribeConfig, sample_image: Path
    ) -> PageContext:
        """Create a sample page context with HTML image references."""
        source_file = temp_dir / "source" / "test_page.md"
        source_file.parent.mkdir(exist_ok=True)

        # Create HTML content with image references (as if processed by markdown plugin)
        content = """<h1>Test Page</h1>

<p>This is a test page with images.</p>

<p><img src="test_image.png" alt="Test Image"></p>

<p>Some more content here.</p>

<p><img src="test_image.png" alt="HTML image"></p>
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

    async def test_extract_image_references(
        self, plugin: ImageEncodingPlugin, page_context: PageContext
    ) -> None:
        """Test extracting image references from HTML content."""
        image_refs = plugin._extract_html_image_references(page_context.content)
        assert len(image_refs) == 1  # Should deduplicate the same image
        assert "test_image.png" in image_refs

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
        assert result_ctx.image_encoding_data.responsive_images is not None
        assert result_ctx.image_encoding_data.image_dimensions is not None

        # Check that images were processed
        processed_images = result_ctx.image_encoding_data.processed_images
        assert "test_image.png" in processed_images

        # Should include supported formats
        formats = processed_images["test_image.png"]
        assert len(formats) > 0  # At least one format should be supported
        if plugin.supports_webp:
            assert "webp" in formats

        # Check responsive images data
        responsive_images = result_ctx.image_encoding_data.responsive_images
        assert "test_image.png" in responsive_images

    async def test_process_page_no_images(
        self, plugin: ImageEncodingPlugin, temp_dir: Path, site_config: ScribeConfig
    ) -> None:
        """Test processing a page with no image references."""
        # Create page context without images
        source_file = temp_dir / "source" / "no_images.md"
        content = "<h1>No Images</h1>\n\n<p>This page has no images.</p>"
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
        resolved_path = plugin._find_image_path("test_image.png", page_context)
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
        # Cache key should be based on relative path with slug formatting
        assert "testimage" in key1  # test_image.png becomes testimage

    async def test_extract_external_images_ignored(
        self, plugin: ImageEncodingPlugin
    ) -> None:
        """Test that external URLs are ignored."""
        content = """
        <img src="https://example.com/image.jpg" alt="External">
        <img src="local_image.jpg" alt="Local">
        <img src="http://example.com/image.png" alt="External HTML">
        <img src="local.png" alt="Local HTML">
        """

        image_refs = plugin._extract_html_image_references(content)
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
        """Test that image paths are rewritten to use picture elements."""
        # Create a fresh page context for this test
        source_file = temp_dir / "source" / "rewrite_test.md"
        source_file.parent.mkdir(exist_ok=True)

        # Create HTML content with original png references
        original_content = """<h1>Test Page</h1>

<p>This is a test page with images.</p>

<p><img src="test_image.png" alt="Test Image"></p>

<p>Some more content here.</p>

<p><img src="test_image.png" alt="HTML image"></p>
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

        # Check that content was modified to use picture elements
        new_content = result_ctx.content

        # Original content should have .png references
        assert "test_image.png" in original_content

        # New content should have picture elements with responsive images
        assert "<picture>" in new_content
        assert "<source" in new_content
        assert "srcset=" in new_content

        # Should have responsive sizes in srcset with slug-based naming
        if plugin.supports_webp:
            # At least some responsive image should be generated
            assert (
                "rewritetest_testimage_" in new_content
            )  # At least one responsive size generated
            assert ".webp" in new_content  # WebP format

        # Should have loading attributes
        assert 'loading="lazy"' in new_content
        assert 'decoding="async"' in new_content

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
        img = pyvips.Image.black(100, 100).ifthenelse([0, 0, 255], [0, 0, 0])
        image_path = sub_dir / "photo.jpg"
        img.write_to_file(str(image_path), Q=95)

        # Create page context with HTML content referencing subdirectory image
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content=(
                '<p><img src="images/gallery/photo.jpg" alt="Gallery photo"></p>'
            ),
            content=('<p><img src="images/gallery/photo.jpg" alt="Gallery photo"></p>'),
        )

        plugin = ImageEncodingPlugin(sample_config, site_config)
        result = await plugin.process(ctx)

        # Should rewrite to use picture element with new flat structure
        assert "<picture>" in result.content
        assert (
            "/images/test_photo_" in result.content
        )  # Should contain responsive images with new naming convention

    async def test_featured_photos_processing(
        self,
        sample_config: ImageEncodingPluginConfig,
        site_config: ScribeConfig,
        temp_dir: Path,
    ) -> None:
        """Test that featured_photos are processed and updated correctly."""
        # Create test images
        img1 = pyvips.Image.black(100, 100).ifthenelse([255, 0, 0], [0, 0, 0])
        img2 = pyvips.Image.black(100, 100).ifthenelse([0, 0, 255], [0, 0, 0])

        image1_path = temp_dir / "static" / "featured1.jpg"
        image2_path = temp_dir / "static" / "featured2.jpg"

        img1.write_to_file(str(image1_path), Q=95)
        img2.write_to_file(str(image2_path), Q=95)

        # Create page context with featured_photos
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content="<p>Some content without images in text</p>",
            content="<p>Some content without images in text</p>",
            featured_photos=["featured1.jpg", "featured2.jpg"],
        )

        plugin = ImageEncodingPlugin(sample_config, site_config)
        result = await plugin.process(ctx)

        # Should process featured_photos and update them to converted paths
        assert len(result.featured_photos) == 2

        # Featured photos should be updated to point to converted images
        converted_photo1 = result.featured_photos[0]
        converted_photo2 = result.featured_photos[1]

        # Should have .webp extension
        assert converted_photo1.endswith(".webp")
        assert converted_photo2.endswith(".webp")

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
        img1 = pyvips.Image.black(100, 100).ifthenelse([255, 0, 0], [0, 0, 0])
        img2 = pyvips.Image.black(100, 100).ifthenelse([0, 0, 255], [0, 0, 0])
        img3 = pyvips.Image.black(100, 100).ifthenelse([0, 255, 0], [0, 0, 0])

        image1_path = temp_dir / "static" / "featured.jpg"
        image2_path = temp_dir / "static" / "content.jpg"
        image3_path = (
            temp_dir / "static" / "both.jpg"
        )  # Used in both featured and content

        img1.write_to_file(str(image1_path), Q=95)
        img2.write_to_file(str(image2_path), Q=95)
        img3.write_to_file(str(image3_path), Q=95)

        # Create page context with both featured_photos and content images (HTML)
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content=(
                '<p><img src="content.jpg" alt="Content image"> '
                '<img src="both.jpg" alt="Shared image"></p>'
            ),
            content=(
                '<p><img src="content.jpg" alt="Content image"> '
                '<img src="both.jpg" alt="Shared image"></p>'
            ),
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
        assert all(photo.endswith(".webp") for photo in result.featured_photos)

        # Should update content with picture elements
        assert "<picture>" in result.content
        assert (
            "test_content_" in result.content or "test_both_" in result.content
        )  # Should have responsive images with new naming convention

    async def test_simple_responsive_img_mode(
        self,
        temp_dir: Path,
        site_config: ScribeConfig,
    ) -> None:
        """Test that use_picture_element=False creates simple img tags with srcset."""
        # Create config with picture element disabled
        config = ImageEncodingPluginConfig(
            name="image_encoding",
            cache_dir=str(temp_dir / "cache"),
            formats=["webp"],
            use_picture_element=False,
            generate_responsive=True,
            responsive_sizes=[400, 800, 1200],
        )

        # Create test image
        img = pyvips.Image.black(1200, 800).ifthenelse([255, 0, 0], [0, 0, 0])
        image_path = temp_dir / "static" / "test.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        img.write_to_file(str(image_path), Q=95)

        # Create page context with HTML content
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content='<p><img src="test.jpg" alt="Test image"></p>',
            content='<p><img src="test.jpg" alt="Test image"></p>',
        )

        plugin = ImageEncodingPlugin(config, site_config)
        result = await plugin.process(ctx)

        # Should create simple img tag with srcset, not picture element
        assert "<picture>" not in result.content
        assert "<source" not in result.content
        assert 'srcset="' in result.content
        assert 'sizes="' in result.content
        # At least some responsive image should be generated
        assert (
            "test_test_" in result.content
        )  # Responsive images with new naming convention
        assert ".webp" in result.content

    async def test_multiple_responsive_sizes_generated(
        self,
        temp_dir: Path,
        site_config: ScribeConfig,
    ) -> None:
        """Test that multiple responsive sizes are actually generated for large images."""
        # Create config with explicit responsive sizes - use smaller, more realistic sizes for testing
        config = ImageEncodingPluginConfig(
            name="image_encoding",
            cache_dir=str(temp_dir / "cache"),
            formats=["webp"],
            quality_webp=85,
            generate_responsive=True,
            responsive_sizes=[400, 600, 800, 1200],  # Smaller set for testing
            verbose=True,  # Enable verbose logging to see what's happening
        )

        # Create a reasonably sized test image (1800x1200) - large enough for all responsive sizes
        # Use a simple solid color image to avoid complex pattern issues
        img = pyvips.Image.black(1800, 1200, bands=3)
        # Add some color to make it a valid RGB image
        img = img + [100, 150, 200]  # Simple way to add color
        image_path = temp_dir / "static" / "test_photo.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        img.write_to_file(str(image_path))

        # Create page context
        source_path = temp_dir / "source" / "test.md"
        source_path.write_text("content")

        ctx = PageContext(
            source_path=source_path,
            relative_path=Path("test.md"),
            output_path=temp_dir / "output" / "test.html",
            raw_content='<p><img src="test_photo.png" alt="Test photo"></p>',
            content='<p><img src="test_photo.png" alt="Test photo"></p>',
            slug="responsive-test",
        )

        plugin = ImageEncodingPlugin(config, site_config)
        result = await plugin.process(ctx)

        # Verify multiple responsive sizes were generated
        assert result.image_encoding_data is not None
        responsive_images = result.image_encoding_data.responsive_images
        assert "test_photo.png" in responsive_images

        generated_sizes = list(responsive_images["test_photo.png"].keys())
        print(f"Generated sizes: {sorted(generated_sizes)}")

        # Should have generated multiple sizes (all that fit within 1800px width)
        expected_sizes = [400, 600, 800, 1200]  # All should fit in 1800px
        assert len(generated_sizes) >= 3, (
            f"Expected at least 3 sizes, got {len(generated_sizes)}: {generated_sizes}"
        )

        # Verify specific sizes are present
        for expected_size in [400, 600, 800]:
            assert expected_size in generated_sizes, (
                f"Missing {expected_size}px size in {generated_sizes}"
            )

        # Check that srcset contains multiple sizes
        srcset_content = result.content
        assert "400w" in srcset_content, "Missing 400w in srcset"
        assert "600w" in srcset_content, "Missing 600w in srcset"
        assert "800w" in srcset_content, "Missing 800w in srcset"

        # Verify files were actually written to output directory
        output_images_dir = temp_dir / "output" / "images"
        assert output_images_dir.exists(), "Output images directory not created"

        output_files = list(output_images_dir.glob("*.webp"))
        print(f"Output files: {[f.name for f in output_files]}")

        # Should have multiple WebP files
        assert len(output_files) >= 3, (
            f"Expected at least 3 output files, got {len(output_files)}"
        )

        # Check specific files exist
        expected_files = [
            "responsive-test_testphoto_400.webp",
            "responsive-test_testphoto_600.webp",
            "responsive-test_testphoto_800.webp",
        ]

        for expected_file in expected_files:
            expected_path = output_images_dir / expected_file
            assert expected_path.exists(), f"Missing output file: {expected_file}"

            # Verify file has content
            assert expected_path.stat().st_size > 0, (
                f"Empty output file: {expected_file}"
            )
