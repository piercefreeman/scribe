"""Tests for the screenshot plugin."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scribe.context import PageContext
from scribe.note_plugins.config import ScreenshotPluginConfig
from scribe.note_plugins.screenshot import ScreenshotPlugin


class TestScreenshotPlugin:
    """Test cases for the ScreenshotPlugin."""

    @pytest.fixture
    def plugin(self):
        """Create a ScreenshotPlugin instance for testing."""
        config = ScreenshotPluginConfig()
        return ScreenshotPlugin(config)

    @pytest.fixture
    def custom_plugin(self):
        """Create a ScreenshotPlugin instance with custom config."""
        config = ScreenshotPluginConfig(
            background_image="/custom/background.jpg",
            wrapper_classes="custom-wrapper bg-blue-500",
            inner_classes="custom-inner flex",
            image_classes="custom-image rounded-lg",
        )
        return ScreenshotPlugin(config)

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

    async def test_screenshot_image_wrapped(self, plugin, base_context):
        """Test that images with 'screenshot' in alt text are wrapped properly."""
        html_content = '<img src="image.png" alt="This is a screenshot of the app">'
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        # Check wrapper div exists
        wrapper = soup.find("div", class_="screenshot")
        assert wrapper is not None
        wrapper_classes = wrapper.get("class")
        assert "relative" in wrapper_classes
        assert "px-6" in wrapper_classes
        assert "py-4" in wrapper_classes
        assert "bg-cover" in wrapper_classes
        assert "bg-center" in wrapper_classes
        assert "screenshot" in wrapper_classes
        assert wrapper.get("style") == "background-image: url('/desktops/sonoma.jpg')"

        # Check inner div exists
        inner = wrapper.find("div", class_="flex")
        assert inner is not None
        inner_classes = inner.get("class")
        assert "flex" in inner_classes
        assert "justify-center" in inner_classes
        assert "items-center" in inner_classes

        # Check image has additional classes
        img = inner.find("img")
        assert img is not None
        img_classes = img.get("class")
        assert "max-w-full" in img_classes
        assert "h-auto" in img_classes
        assert "rounded-sm" in img_classes

    async def test_non_screenshot_image_unchanged(self, plugin, base_context):
        """Test that regular images are not wrapped."""
        html_content = '<img src="image.png" alt="Regular image">'
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        # Should not have wrapper div
        wrapper = soup.find("div", class_="screenshot")
        assert wrapper is None

        # Image should remain unchanged
        img = soup.find("img")
        assert img is not None
        assert img.get("src") == "image.png"
        assert img.get("alt") == "Regular image"

    async def test_case_insensitive_screenshot_detection(self, plugin, base_context):
        """Test that screenshot detection is case insensitive."""
        test_cases = [
            "Screenshot of the interface",
            "SCREENSHOT showing the feature",
            "This is a ScreenShot example",
            "Application screenshot here",
        ]

        for alt_text in test_cases:
            html_content = f'<img src="test.png" alt="{alt_text}">'
            base_context.content = html_content

            result = await plugin.process(base_context)
            soup = BeautifulSoup(result.content, "html.parser")

            wrapper = soup.find("div", class_="screenshot")
            assert wrapper is not None, f"Failed for alt text: {alt_text}"

    async def test_multiple_images_mixed(self, plugin, base_context):
        """Test processing multiple images with mixed screenshot/regular images."""
        html_content = """
        <img src="regular1.png" alt="Regular image">
        <img src="screen1.png" alt="Screenshot of feature A">
        <img src="regular2.png" alt="Another regular image">
        <img src="screen2.png" alt="App screenshot showing menu">
        """
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        # Should have exactly 2 wrapper divs (for screenshots)
        wrappers = soup.find_all("div", class_="screenshot")
        assert len(wrappers) == 2

        # All images should still be present
        images = soup.find_all("img")
        assert len(images) == 4

        # Check that correct images are wrapped
        wrapped_imgs = [wrapper.find("img") for wrapper in wrappers]
        wrapped_srcs = [img.get("src") for img in wrapped_imgs]
        assert "screen1.png" in wrapped_srcs
        assert "screen2.png" in wrapped_srcs

    async def test_custom_configuration(self, custom_plugin, base_context):
        """Test that custom configuration is applied correctly."""
        html_content = '<img src="test.png" alt="Screenshot test">'
        base_context.content = html_content

        result = await custom_plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        # Check custom wrapper classes
        wrapper = soup.find("div")
        assert "custom-wrapper" in wrapper.get("class")
        assert "bg-blue-500" in wrapper.get("class")
        assert wrapper.get("style") == "background-image: url('/custom/background.jpg')"

        # Check custom inner classes
        inner = wrapper.find("div")
        assert "custom-inner" in inner.get("class")
        assert "flex" in inner.get("class")

        # Check custom image classes
        img = inner.find("img")
        assert "custom-image" in img.get("class")
        assert "rounded-lg" in img.get("class")

    async def test_preserve_existing_image_classes(self, plugin, base_context):
        """Test that existing image classes are preserved."""
        html_content = (
            '<img src="test.png" alt="Screenshot" class="existing-class another-class">'
        )
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        img = soup.find("img")
        img_classes = img.get("class")

        # Should have both existing and new classes
        assert "existing-class" in img_classes
        assert "another-class" in img_classes
        assert "max-w-full" in img_classes
        assert "h-auto" in img_classes
        assert "rounded-sm" in img_classes

    async def test_preserve_existing_image_attributes(self, plugin, base_context):
        """Test that existing image attributes are preserved."""
        html_content = """
        <img src="test.png"
             alt="Screenshot of app"
             width="800"
             height="600"
             data-custom="value"
             title="App Screenshot">
        """
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        img = soup.find("img")
        assert img.get("src") == "test.png"
        assert img.get("alt") == "Screenshot of app"
        assert img.get("width") == "800"
        assert img.get("height") == "600"
        assert img.get("data-custom") == "value"
        assert img.get("title") == "App Screenshot"

    async def test_empty_content(self, plugin, base_context):
        """Test handling of empty content."""
        base_context.content = ""
        result = await plugin.process(base_context)
        assert result.content == ""

    async def test_no_images(self, plugin, base_context):
        """Test handling of content with no images."""
        html_content = "<p>This is just text content with no images.</p>"
        base_context.content = html_content

        result = await plugin.process(base_context)
        assert result.content == html_content

    async def test_malformed_html(self, plugin, base_context):
        """Test handling of malformed HTML."""
        html_content = '<img src="test.png" alt="Screenshot" unclosed>'
        base_context.content = html_content

        result = await plugin.process(base_context)
        # Should not crash and should still wrap the image
        soup = BeautifulSoup(result.content, "html.parser")
        wrapper = soup.find("div", class_="screenshot")
        assert wrapper is not None

    async def test_image_without_alt_attribute(self, plugin, base_context):
        """Test handling of images without alt attributes."""
        html_content = '<img src="test.png">'
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        # Should not be wrapped since no alt text
        wrapper = soup.find("div", class_="screenshot")
        assert wrapper is None

    async def test_complex_html_structure(self, plugin, base_context):
        """Test with complex HTML structure."""
        html_content = """
        <div class="container">
            <h1>Documentation</h1>
            <p>Here's how the app works:</p>
            <figure>
                <img src="ui.png" alt="Screenshot of the main interface">
                <figcaption>Main interface</figcaption>
            </figure>
            <p>More content here.</p>
        </div>
        """
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        # Should still wrap the screenshot
        wrapper = soup.find("div", class_="screenshot")
        assert wrapper is not None

        # Should preserve overall structure
        container = soup.find("div", class_="container")
        assert container is not None
        assert soup.find("h1") is not None
        assert soup.find("figcaption") is not None

    async def test_plugin_preserves_other_context_fields(self, plugin, base_context):
        """Test that the plugin only modifies content, not other context fields."""
        html_content = '<img src="test.png" alt="Screenshot example">'
        base_context.content = html_content
        base_context.title = "Test Title"
        base_context.tags = ["test", "screenshot"]

        result = await plugin.process(base_context)

        assert result.title == "Test Title"
        assert result.tags == ["test", "screenshot"]
        assert result.source_path == base_context.source_path
        assert result.content != html_content  # Content should be modified

    @pytest.mark.parametrize(
        "alt_text",
        [
            "screenshot",
            "Screenshot",
            "SCREENSHOT",
            "My screenshot here",
            "This contains screenshot text",
            "screenshot-example",
            "app_screenshot_final",
        ],
    )
    async def test_screenshot_detection_variations(
        self, plugin, base_context, alt_text
    ):
        """Test various ways 'screenshot' can appear in alt text."""
        html_content = f'<img src="test.png" alt="{alt_text}">'
        base_context.content = html_content

        result = await plugin.process(base_context)
        soup = BeautifulSoup(result.content, "html.parser")

        wrapper = soup.find("div", class_="screenshot")
        assert wrapper is not None, f"Failed to detect screenshot in: {alt_text}"
