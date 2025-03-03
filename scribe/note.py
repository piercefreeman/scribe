from datetime import datetime
from os import getenv
from pathlib import Path
from re import sub
from textwrap import dedent

from bs4 import BeautifulSoup
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.extensions.tables import TableExtension
from pydantic import BaseModel, ConfigDict, model_validator

from scribe.asset import Asset
from scribe.backup import backup_file
from scribe.constants import READING_WPM
from scribe.logging import LOGGER
from scribe.markdown import MarkdownParser
from scribe.metadata import FeaturedPhotoPayload, NoteMetadata
from scribe.parsers import (
    InvalidMetadataFormatError,
    MissingMetadataBlockError,
    NoTitleError,
    get_raw_text,
    get_simple_content,
    parse_metadata,
    parse_title,
)

MEDIA_SUFFIX_WHITELIST = {".png", ".jpeg", ".jpg"}


class Note(BaseModel):
    """
    A dynamic entry of a note. Handles the processing of raw markdown data into
    a python object that's able to be inserted into the template engine.

    """

    text: str
    """Raw markdown content"""

    title: str
    """Title of the note"""

    metadata: NoteMetadata
    """Metadata for the note"""

    simple_content: str
    """Text-only content with markdown stripped, mostly used for previews"""

    filename: str | None = None
    """Filename of the note, only set if the note is on disk"""

    path: Path | None = None
    """Path to the note, only set if the note is on disk"""

    #
    # Computed fields that are validated at creation time
    #

    assets: list[Asset] = []
    """List of all assets (images, etc.) referenced in the note's content"""

    featured_assets: list[FeaturedPhotoPayload] = []
    """List of featured photos specifically designated for photo collages or prominent display"""

    webpage_path: str = ""
    """URL-friendly path generated from the note's title for web routing"""

    html_content: str = ""
    """Rendered HTML content of the note, processed from markdown with extensions"""

    read_time_minutes: int = 0
    """Estimated reading time in minutes based on word count"""

    visible_tag: str | None = None
    """Status tag that's only visible in development environment"""

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_file(cls, path: Path):
        with open(path) as file:
            text = file.read().strip()

        try:
            return cls.from_text(
                path=path,
                text=text,
            )
        except NoTitleError:
            # Backup the original file
            backup_path = backup_file(path)
            LOGGER.warning(f"Backed up original file to {backup_path}")

            # Add a stub title with the current date
            stub_header = f"# Draft Note {datetime.now().strftime('%Y-%m-%d')}\n\n"
            new_text = stub_header + text

            # Write the modified file
            with open(path, "w") as f:
                f.write(new_text)

            LOGGER.warning(f"Added stub title to {path}")
            return cls.from_file(path)
        except MissingMetadataBlockError:
            # Backup the original file
            backup_path = backup_file(path)
            LOGGER.warning(f"Backed up original file to {backup_path}")

            # Add a stub metadata block after the title
            lines = text.split("\n")
            first_line = lines[0]  # Title should be here since NoTitleError would have caught it
            rest_of_file = "\n".join(lines[1:])

            stub_metadata = dedent(
                f"""
                meta:
                    date: {datetime.now().strftime("%B %-d, %Y")}
                    status: scratch
                """
            )
            new_text = f"{first_line}\n{stub_metadata}\n{rest_of_file}"

            # Write the modified file
            with open(path, "w") as f:
                f.write(new_text)

            LOGGER.warning(f"Added stub metadata block to {path}")
            return cls.from_text(
                path=path,
                text=new_text,
            )
        except InvalidMetadataFormatError as e:
            # Re-raise with more context about which file failed
            raise InvalidMetadataFormatError(f"Invalid metadata in {path}: {str(e)}") from e

    @classmethod
    def from_text(cls, path: Path | str, text: str):
        parsed_title = parse_title(text)
        parsed_metadata = parse_metadata(text)

        path_obj = Path(path)

        return cls(
            text=get_raw_text(text, [parsed_title, parsed_metadata]),
            title=parsed_title.result,
            metadata=parsed_metadata.result,
            path=path_obj,
            filename=path_obj.with_suffix("").name,
            simple_content=get_simple_content(text),
        )

    def model_copy(self, update: dict) -> "Note":  # type: ignore
        # If we are updating the text, we need to recompute the html content
        if "text" in update or "metadata" in update or "assets" in update:
            text = update.get("text", self.text)
            metadata = update.get("metadata", self.metadata)
            assets = update.get("assets", self.assets)
            update["html_content"] = self.compute_html_content(text, metadata, assets)

        return super().model_copy(update=update)

    def has_footnotes(self) -> bool:
        """Check if the note contains any footnotes."""
        return MarkdownParser.has_footnotes(self.text)

    def get_preview(self) -> str:
        return "\n".join(self.metadata.subtitle)

    @model_validator(mode="after")
    def compute_assets(self) -> "Note":  # noqa: N805
        """Compute assets referenced in the note's text or metadata."""
        if not self.path:
            LOGGER.warning(f"Note {self} has no path; cannot fetch assets.")
            object.__setattr__(self, "assets", [])
            return self

        referenced_images = {
            Path(path).name for path in MarkdownParser.extract_referenced_images(self.text)
        }
        featured_photos = {
            Path(photo.path if isinstance(photo, FeaturedPhotoPayload) else photo).name
            for photo in self.metadata.featured_photos
        }
        all_referenced = referenced_images | featured_photos
        LOGGER.debug(f"All referenced images for {self.title}: {all_referenced}")

        assets = []
        for path in self.path.parent.iterdir():
            if path.suffix.lower() in MEDIA_SUFFIX_WHITELIST and path.name in all_referenced:
                assets.append(Asset.from_note(self, path))
            elif path.suffix.lower() in MEDIA_SUFFIX_WHITELIST:
                LOGGER.debug(f"Skipping unreferenced asset: {path}")

        object.__setattr__(self, "assets", list(set(assets)))
        return self

    @model_validator(mode="after")
    def compute_featured_assets(self) -> "Note":  # noqa: N805
        """Compute featured assets for photo collages."""
        featured_photos = []
        if not self.path:
            LOGGER.warning(f"Note {self} has no path; cannot fetch featured assets.")
            object.__setattr__(self, "featured_assets", featured_photos)
            return self

        for photo_definition in self.metadata.featured_photos:
            featured_payload: FeaturedPhotoPayload | None = None

            if isinstance(photo_definition, str):
                featured_payload = FeaturedPhotoPayload(path=photo_definition)
            elif isinstance(photo_definition, FeaturedPhotoPayload):
                featured_payload = photo_definition
            else:
                raise ValueError(f"Unknown payload type: {type(photo_definition)}")

            full_path = Path(self.path).parent / featured_payload.path
            if not full_path.exists():
                raise ValueError(f"Unknown path: {full_path}")

            featured_payload.asset = Asset.from_note(self, full_path)
            featured_photos.append(featured_payload)

        object.__setattr__(self, "featured_assets", featured_photos)
        return self

    @model_validator(mode="before")
    def compute_webpage_path(cls, values: dict) -> dict:  # noqa: N805
        """Compute the webpage path based on the note's title."""
        if not values.get("title"):
            raise ValueError(f"No header found for: {values.get('filename')}")

        header = values["title"].lower()
        header = sub(r"[^a-zA-Z0-9\s]", "", header)
        header_tokens = header.split()[:20]
        values["webpage_path"] = "-".join(header_tokens)
        return values

    @model_validator(mode="before")
    def compute_read_time(cls, values: dict) -> dict:  # noqa: N805
        """Compute estimated reading time in minutes."""
        words = len(values["text"].split())
        values["read_time_minutes"] = (words // READING_WPM) + 1
        return values

    @model_validator(mode="before")
    def compute_visible_tag(cls, values: dict) -> dict:  # noqa: N805
        """Compute the visible tag based on environment and status."""
        values["visible_tag"] = (
            str(values["metadata"].status.value)
            if getenv("SCRIBE_ENVIRONMENT") == "DEVELOPMENT"
            else None
        )
        return values

    @model_validator(mode="before")
    def cache_html_content(cls, values: dict) -> dict:  # noqa: N805
        """
        Compute the HTML content for this note. This is done lazily since HTML generation
        can be expensive and may not always be needed.
        """
        values["html_content"] = cls.compute_html_content(
            values["text"], values["metadata"], values.get("assets", [])
        )
        return values

    @classmethod
    def compute_html_content(cls, text: str, metadata: NoteMetadata, assets: list[Asset]) -> str:
        html = markdown(
            text,
            extensions=[
                CodeHiliteExtension(use_pygments=True),
                FencedCodeExtension(),
                FootnoteExtension(BACKLINK_TEXT="↢"),
                TableExtension(),
            ],
        )

        content = BeautifulSoup(html, "html.parser")

        # Style images - these should be located somewhere in the html dom (like in a template
        # tag - so tailwind can pick up on them)
        for img in content.find_all("img"):
            image_classes = img.get("class", [])

            # Travel specific styling
            if "travel" in metadata.tags:
                image_classes.append("large-image")
            else:
                image_classes.append("small-image")

            img["class"] = " ".join(image_classes)

            # Add srcset if the image has DPI variants
            src = img.get("src", "")
            if src:
                # Find the corresponding asset
                for asset in assets:
                    if src.endswith(asset.remote_preview_path):
                        if asset.resolution_map:
                            srcset_parts = []
                            for dpi, descriptor in asset.resolution_map.items():
                                srcset_parts.append(
                                    f"{asset.get_remote_dpi_path(dpi)} {descriptor}"
                                )
                            img["srcset"] = ", ".join(srcset_parts)
                            break

        return str(content)
