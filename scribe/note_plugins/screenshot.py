"""Screenshot plugin for adding synthetic backgrounds to screenshot images."""

from bs4 import BeautifulSoup, Tag

from scribe.context import PageContext
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import PluginName, ScreenshotPluginConfig


class ScreenshotPlugin(NotePlugin[ScreenshotPluginConfig]):
    """Plugin to add synthetic backgrounds to images with 'screenshot' in alt text."""

    name = PluginName.SCREENSHOT

    def __init__(self, config: ScreenshotPluginConfig) -> None:
        super().__init__(config)

        # Get configuration values directly from typed config
        self.background_image = config.background_image
        self.wrapper_classes = config.wrapper_classes
        self.inner_classes = config.inner_classes
        self.image_classes = config.image_classes

    async def process(self, ctx: PageContext) -> PageContext:
        """Process HTML content to add backgrounds to screenshot images."""
        content = ctx.content

        # Parse HTML content
        soup = BeautifulSoup(content, "html.parser")

        # Find all img tags
        images = soup.find_all("img")

        for img in images:
            if isinstance(img, Tag):
                alt_text_raw = img.get("alt", "")
                if isinstance(alt_text_raw, str):
                    alt_text = alt_text_raw.lower()

                    # Check if this is a screenshot by looking at the alt text
                    if "screenshot" in alt_text:
                        self._wrap_screenshot_image(img)

        ctx.content = str(soup)
        return ctx

    def _wrap_screenshot_image(self, img: Tag) -> None:
        """Wrap a screenshot image with synthetic background elements."""
        # Get the soup object from the img element
        soup = img.find_parent()
        while soup and soup.parent:
            soup = soup.parent

        if not soup or not hasattr(soup, "new_tag"):
            # If we can't find the root soup, create a new one
            temp_soup = BeautifulSoup("", "html.parser")
            # Use the temp soup to create tags
            wrapper_div = temp_soup.new_tag("div")
            inner_div = temp_soup.new_tag("div")
        else:
            # Create a wrapper div for the screenshot with background
            wrapper_div = soup.new_tag("div")
            inner_div = soup.new_tag("div")

        wrapper_div["class"] = self.wrapper_classes
        wrapper_div["style"] = f"background-image: url('{self.background_image}')"

        # Create an inner div for centering the screenshot
        inner_div["class"] = self.inner_classes

        # Add screenshot-specific styling to the image
        existing_classes_raw = img.get("class")
        existing_classes: list[str] = []

        if isinstance(existing_classes_raw, str):
            existing_classes = existing_classes_raw.split()
        elif isinstance(existing_classes_raw, list):
            existing_classes = existing_classes_raw

        # Add new classes while preserving existing ones
        new_classes = existing_classes + self.image_classes.split()
        img["class"] = " ".join(new_classes)

        # Wrap the image: img -> inner_div -> wrapper_div
        img.wrap(inner_div)
        inner_div.wrap(wrapper_div)
