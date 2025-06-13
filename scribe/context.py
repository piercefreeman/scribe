"""Context dataclass for passing page information through plugins."""

import logging
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class PageStatus(Enum):
    """Status enum for page publication state."""

    PUBLISH = "publish"
    DRAFT = "draft"
    SCRATCH = "scratch"


class DateData(BaseModel):
    """Typed data structure for date plugin information."""

    raw: str
    parsed: datetime
    formatted: str
    iso: str


class ImageEncodingData(BaseModel):
    """Typed data structure for image encoding plugin information."""

    processed_images: dict[str, list[str]]
    formats: list[str]
    # Simplified responsive image data (WebP only)
    responsive_images: dict[str, dict[int, str]] = {}  # {src: {width: path}}
    image_dimensions: dict[str, tuple[int, int]] = {}  # {src: (width, height)}


class FrontmatterData(BaseModel):
    """Validated frontmatter structure for page metadata."""

    # Core content metadata
    title: str | None = None
    description: str | None = None
    date: str | None = None
    author: str | None = None
    slug: str | None = None

    # Content organization
    tags: list[str] = []
    status: PageStatus = PageStatus.SCRATCH

    # Template configuration
    template: str = "default.html"
    layout: str | None = None

    # URLs and linking
    external_link: str | None = None

    featured_photos: list[str] = []

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> list[str]:
        """Parse tags from various input formats."""
        if v is None:
            return []
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(",")]
        if isinstance(v, list):
            return [str(tag).strip() for tag in v]
        return []

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Any) -> PageStatus:
        """Parse and validate page status."""
        if isinstance(v, PageStatus):
            return v
        if isinstance(v, str):
            try:
                return PageStatus(v.lower())
            except ValueError:
                logger.warning(f"Invalid status '{v}', defaulting to 'scratch'")
                return PageStatus.SCRATCH
        return PageStatus.SCRATCH

    model_config = {"extra": "allow"}


class PageContext(BaseModel):
    """Context object passed through plugins containing page metadata and content."""

    # File information
    source_path: Path
    relative_path: Path
    output_path: Path

    # Raw content from file
    raw_content: str

    # Processed content
    content: str = ""

    # Metadata (derived from frontmatter or extracted from content)
    title: str | None = None
    description: str | None = None
    tags: list[str] = []
    date: str | None = None
    author: str | None = None
    slug: str | None = None
    featured_photos: list[str] = []

    # URLs and paths
    external_link: str | None = None

    # Template information
    template: str = "default.html"
    layout: str | None = None

    # Plugin data - serializable data
    frontmatter: FrontmatterData = Field(default_factory=FrontmatterData)
    date_data: DateData | None = None
    image_encoding_data: ImageEncodingData | None = None

    # Build information
    status: PageStatus = PageStatus.SCRATCH
    modified_time: float | None = None

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def validate_and_initialize(self) -> "PageContext":
        """Initialize computed fields after model creation."""
        # Generate slug if not set
        if not self.slug:
            self.slug = self._generate_slug()
        return self

    def _generate_slug(self) -> str:
        """Generate URL slug from file path or title."""
        if self.frontmatter.slug:
            return self.frontmatter.slug

        # Generate slug from title if available, otherwise use filename
        if self.title:
            return self.generate_slug_from_text(self.title)

        # Use filename without extension as slug
        return self.generate_slug_from_text(self.relative_path.stem)

    @staticmethod
    def generate_slug_from_text(text: str) -> str:
        """Generate URL-safe slug from text.

        This is the consolidated slug generation logic used by both
        context initialization and the slug plugin.
        """
        if not text:
            return ""

        slug = text.lower().replace(" ", "-")
        # Remove special characters, keep only alphanumeric and hyphens
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        # Remove multiple consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def extract_title_from_content(self) -> tuple[str, str]:
        """Extract title from first line of content with # prefix.

        Returns tuple of (title, remaining_content).
        Raises ValueError if title cannot be extracted.

        This is the consolidated title extraction logic used by
        the title plugin.
        """
        lines = self.content.splitlines()

        if not lines:
            raise ValueError("Content is empty - cannot extract title")

        first_line = lines[0].strip()

        # Check if first line starts with # (markdown header)
        if not first_line.startswith("#"):
            raise ValueError("First line must start with '#' to be used as title")

        # Extract title by removing # prefix and any extra whitespace
        title_match = re.match(r"^#+\s*(.+)", first_line)
        if not title_match:
            raise ValueError("Invalid title format - no content found after '#'")

        title = title_match.group(1).strip()
        if not title:
            raise ValueError("Title cannot be empty after '#' prefix")

        # Remove the title line from content
        remaining_lines = lines[1:]
        remaining_content = "\n".join(remaining_lines)

        return title, remaining_content

    # Helper methods for working with Path objects (keeping for compatibility)
    @property
    def source_path_obj(self) -> Path:
        """Get source_path as a Path object."""
        return self.source_path

    @property
    def relative_path_obj(self) -> Path:
        """Get relative_path as a Path object."""
        return self.relative_path

    @property
    def output_path_obj(self) -> Path:
        """Get output_path as a Path object."""
        return self.output_path
