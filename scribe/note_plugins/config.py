"""Plugin configuration models."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from scribe.plugins import BasePluginConfig, PluginNameEnum


class PluginName(PluginNameEnum):
    """Enum for plugin names."""

    FRONTMATTER = "frontmatter"
    FOOTNOTES = "footnotes"
    LINK_RESOLUTION = "link_resolution"
    MARKDOWN = "markdown"
    DATE = "date"
    SCREENSHOT = "screenshot"
    SNAPSHOT = "snapshot"
    IMAGE_ENCODING = "image_encoding"


class BaseNotePluginConfig(BasePluginConfig[PluginName]):
    """Base configuration for all note plugins."""

    name: PluginName


class FrontmatterPluginConfig(BaseNotePluginConfig):
    """Configuration for the frontmatter plugin.

    Example YAML configuration:
    ```yaml
    frontmatter:
      name: frontmatter
      enabled: true
    ```
    """

    name: Literal[PluginName.FRONTMATTER] = PluginName.FRONTMATTER
    before_dependencies: list[PluginName] = [PluginName.MARKDOWN]


class FootnotesPluginConfig(BaseNotePluginConfig):
    """Configuration for the footnotes plugin.

    Example YAML configuration:
    ```yaml
    footnotes:
      name: footnotes
      enabled: true
    ```
    """

    name: Literal[PluginName.FOOTNOTES] = PluginName.FOOTNOTES
    before_dependencies: list[PluginName] = [PluginName.MARKDOWN]


class LinkResolutionPluginConfig(BaseNotePluginConfig):
    """Configuration for the link resolution plugin.

    Example YAML configuration:
    ```yaml
    link_resolution:
      name: link_resolution
      enabled: true
    ```
    """

    name: Literal[PluginName.LINK_RESOLUTION] = PluginName.LINK_RESOLUTION
    before_dependencies: list[PluginName] = [PluginName.MARKDOWN]


class MarkdownPluginConfig(BaseNotePluginConfig):
    """Configuration for the markdown plugin.

    Example YAML configuration:
    ```yaml
    markdown:
      name: markdown
      enabled: true
    ```
    """

    name: Literal[PluginName.MARKDOWN] = PluginName.MARKDOWN


class DatePluginConfig(BaseNotePluginConfig):
    """Configuration for the date plugin.

    Example YAML configuration:
    ```yaml
    date:
      name: date
      enabled: true
    ```
    """

    name: Literal[PluginName.DATE] = PluginName.DATE
    before_dependencies: list[PluginName] = [PluginName.MARKDOWN]


class ScreenshotPluginConfig(BaseNotePluginConfig):
    """Configuration for the screenshot plugin.

    Example YAML configuration:
    ```yaml
    screenshot:
      name: screenshot
      enabled: true
      background_image: "/desktops/sonoma.jpg"
      wrapper_classes: "relative px-6 py-4 bg-cover bg-center screenshot"
      inner_classes: "flex justify-center items-center"
      image_classes: "max-w-full h-auto rounded-sm"
    ```
    """

    name: Literal[PluginName.SCREENSHOT] = PluginName.SCREENSHOT
    after_dependencies: list[PluginName] = [PluginName.MARKDOWN]

    background_image: str = "/desktops/sonoma.jpg"
    wrapper_classes: str = "relative px-6 py-4 bg-cover bg-center screenshot"
    inner_classes: str = "flex justify-center items-center"
    image_classes: str = "max-w-full h-auto rounded-sm"


class SnapshotPluginConfig(BaseNotePluginConfig):
    """Configuration for the snapshot plugin.

    Example YAML configuration:
    ```yaml
    snapshot:
      name: snapshot
      enabled: true
      snapshot_dir: "./snapshots"  # Required field
      snapshots_output_dir: "snapshots"  # Optional output directory in build
      max_concurrent: 5
      max_attempts: 3
      headful: false
    ```
    """

    name: Literal[PluginName.SNAPSHOT] = PluginName.SNAPSHOT
    after_dependencies: list[PluginName] = [PluginName.MARKDOWN]

    snapshot_dir: Path = Field(
        ..., description="Directory to store snapshots (required)"
    )
    snapshots_output_dir: str = Field(
        default="snapshots",
        description="Output directory name in build output for snapshots",
    )
    max_concurrent: int = Field(default=5, description="Maximum concurrent snapshots")
    max_attempts: int = Field(default=3, description="Maximum retry attempts per URL")
    headful: bool = Field(default=False, description="Show browser during snapshots")


class ImageEncodingPluginConfig(BaseNotePluginConfig):
    """Configuration for the image encoding plugin.

    Example YAML configuration:
    ```yaml
    image_encoding:
      name: image_encoding
      enabled: true
      cache_dir: ".image_cache"
      formats:
        - "avif"
        - "webp"
      quality_avif: 65
      quality_webp: 85
      max_width: null
      max_height: null
      generate_responsive: true
      responsive_sizes:
        - 400
        - 600
        - 800
        - 1200
        - 1600
        - 2400
      default_sizes: "(max-width: 400px) 100vw, (max-width: 800px) 50vw, 33vw"
      use_picture_element: true
      add_loading_lazy: true
      verbose: false
    ```
    """

    name: Literal[PluginName.IMAGE_ENCODING] = PluginName.IMAGE_ENCODING
    after_dependencies: list[PluginName] = [PluginName.MARKDOWN]

    cache_dir: Path = Field(
        default=Path(".image_cache"), description="Directory to cache processed images"
    )
    formats: list[Literal["avif", "webp"]] = Field(
        default_factory=lambda: ["avif", "webp"],
        description="Target formats to generate (in order of preference)",
    )
    quality_avif: int = Field(
        default=65, ge=1, le=100, description="AVIF quality setting (1-100)"
    )
    quality_webp: int = Field(
        default=85, ge=1, le=100, description="WebP quality setting (1-100)"
    )
    max_width: int | None = Field(
        default=None, description="Maximum width for resizing images"
    )
    max_height: int | None = Field(
        default=None, description="Maximum height for resizing images"
    )
    generate_responsive: bool = Field(
        default=True, description="Generate responsive image sizes"
    )
    responsive_sizes: list[int] = Field(
        default_factory=lambda: [400, 600, 800, 1200, 1600, 2400],
        description="Responsive image widths to generate (retina-optimized)",
    )
    default_sizes: str = Field(
        default="(max-width: 400px) 100vw, (max-width: 800px) 50vw, 33vw",
        description="Default sizes attribute for responsive images",
    )
    use_picture_element: bool = Field(
        default=True, description="Use <picture> element for enhanced browser support"
    )
    add_loading_lazy: bool = Field(
        default=True, description="Add loading='lazy' to img elements"
    )
    verbose: bool = Field(default=False, description="Enable verbose logging")


PluginConfig = Annotated[
    FrontmatterPluginConfig
    | FootnotesPluginConfig
    | LinkResolutionPluginConfig
    | MarkdownPluginConfig
    | DatePluginConfig
    | ScreenshotPluginConfig
    | SnapshotPluginConfig
    | ImageEncodingPluginConfig,
    Field(discriminator="name"),
]
