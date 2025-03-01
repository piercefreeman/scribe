from datetime import datetime
from logging import warning
from os import environ
from pathlib import Path
from re import sub
from textwrap import dedent
from typing import Optional

from bs4 import BeautifulSoup
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.extensions.tables import TableExtension

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


class Note:
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

    filename: str | None
    """Filename of the note, only set if the note is on disk"""

    path: Path | None
    """Path to the note, only set if the note is on disk"""

    def __init__(
        self,
        text: str,
        title: str,
        simple_content: str,
        metadata: NoteMetadata,
        filename: str | None = None,
        path: Optional[Path | str] = None,
    ):
        self.text = text
        self.title = title
        self.simple_content = simple_content
        self.metadata = metadata
        self.filename = filename
        self.path = Path(path) if path else None

        self._html_content: str | None = None

    @property
    def html_content(self) -> Optional[str]:
        """Get the cached HTML content if it exists."""
        return self._html_content

    @html_content.setter
    def html_content(self, content: str) -> None:
        """Set the cached HTML content."""
        self._html_content = content

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
            warning(f"Backed up original file to {backup_path}")

            # Add a stub title with the current date
            stub_header = f"# Draft Note {datetime.now().strftime('%Y-%m-%d')}\n\n"
            new_text = stub_header + text

            # Write the modified file
            with open(path, "w") as f:
                f.write(new_text)

            warning(f"Added stub title to {path}")
            return cls.from_file(path)
        except MissingMetadataBlockError:
            # Backup the original file
            backup_path = backup_file(path)
            warning(f"Backed up original file to {backup_path}")

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

            warning(f"Added stub metadata block to {path}")
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

    @property
    def assets(self) -> list[Asset]:
        """
        Get a list of assets that are referenced in the note's text or metadata.
        This includes:
        1. Images referenced in the markdown/HTML content
        2. Featured photos from the metadata
        """
        if not self.path:
            warning(f"Note {self} has no path; cannot fetch assets.")
            return []

        # Get all referenced image paths
        referenced_images = MarkdownParser.extract_referenced_images(self.text)

        # Add featured photos from metadata
        featured_photos = {
            Path(photo.path if isinstance(photo, FeaturedPhotoPayload) else photo).name
            for photo in self.metadata.featured_photos
        }

        all_referenced = referenced_images | featured_photos
        LOGGER.debug(f"All referenced images for {self.title}: {all_referenced}")

        # Only process images that are referenced and match our allowed file suffixes
        assets = []

        for path in self.path.parent.iterdir():
            if path.suffix.lower() in MEDIA_SUFFIX_WHITELIST and path.name in all_referenced:
                assets.append(Asset(self, path))
            elif path.suffix.lower() in MEDIA_SUFFIX_WHITELIST:
                LOGGER.debug(f"Skipping unreferenced asset: {path}")

        # De-duplicate the full images and previews
        return list(set(assets))

    @property
    def featured_assets(self) -> list[FeaturedPhotoPayload]:
        """
        Featured assets are located on photo collages. This function
        parses the user payloads, which can be either a raw string or a payload
        that customizes more metadata about how the photo is featured.

        It returns a normalzied FeaturedPhotoPayload with an asset attached.

        """
        # While technically the featured assets appear within the text, we can't get the absolute
        # path to the images without the note also having a path
        if not self.path:
            warning(f"Note {self} has no path; cannot fetch featured assets.")
            return []

        featured_photos: list[FeaturedPhotoPayload] = []
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

            featured_payload.asset = Asset(self, full_path)
            featured_photos.append(featured_payload)

        return featured_photos

    @property
    def webpage_path(self) -> str:
        """
        Get the desired webpage path for this note. This path is based
        on a cleaned version of the header, so conflicts might occur.

        """
        # Require each post to have a header
        if not self.title:
            raise ValueError(f"No header found for: {self.filename}")

        # Published notes should have a human readible URL
        header = self.title.lower()
        header = sub(r"[^a-zA-Z0-9\s]", "", header)
        header_tokens = header.split()[:20]
        return "-".join(header_tokens)

    def get_html(self) -> str:
        """
        Get the HTML content for this note. If we've already processed it during build,
        return the cached version, otherwise generate it.
        """
        if self._html_content is not None:
            return self._html_content

        html = markdown(
            self.text,
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
            if "travel" in self.metadata.tags:
                image_classes.append("large-image")
            else:
                image_classes.append("small-image")

            img["class"] = " ".join(image_classes)

        self._html_content = str(content)
        return self._html_content

    def has_footnotes(self):
        """Check if the note contains any footnotes."""
        return MarkdownParser.has_footnotes(self.text)

    def get_preview(self):
        return "\n".join(self.metadata.subtitle)

    @property
    def read_time_minutes(self):
        words = len(self.text.split())
        return (words // READING_WPM) + 1

    @property
    def visible_tag(self):
        # Only show post status during development
        if environ["SCRIBE_ENVIRONMENT"] == "DEVELOPMENT":
            return str(self.metadata.status.value)
        return None
