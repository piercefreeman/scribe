from datetime import datetime
from logging import warning
from os import environ
from pathlib import Path
from re import sub
from typing import Optional

from bs4 import BeautifulSoup
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.extensions.tables import TableExtension

from scribe.asset import Asset
from scribe.backup import backup_file
from scribe.metadata import FeaturedPhotoPayload, NoteMetadata
from scribe.parsers import (
    InvalidMetadataFormatException,
    MissingMetadataBlockException,
    NoTitleException,
    get_raw_text,
    get_simple_content,
    parse_metadata,
    parse_title,
)


class Note:
    """
    A dynamic entry of a note. Handles the processing of raw markdown data into
    a python object that's able to be inserted into the template engine.

    """

    text: str

    title: str
    metadata: NoteMetadata

    # Text-only content with markdown stripped, mostly used for previews
    simple_content: str

    filename: str | None = None
    path: Path | None = None
    _html_content: Optional[str] = None

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
        except NoTitleException:
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
            return cls.from_text(
                path=path,
                text=new_text,
            )
        except MissingMetadataBlockException:
            # Backup the original file
            backup_path = backup_file(path)
            warning(f"Backed up original file to {backup_path}")

            # Add a stub metadata block after the title
            lines = text.split("\n")
            first_line = lines[
                0
            ]  # Title should be here since NoTitleException would have caught it
            rest_of_file = "\n".join(lines[1:])

            stub_metadata = f"""
meta:
    date: {datetime.now().strftime("%B %-d, %Y")}
    status: draft
"""
            new_text = f"{first_line}\n{stub_metadata}\n{rest_of_file}"

            # Write the modified file
            with open(path, "w") as f:
                f.write(new_text)

            warning(f"Added stub metadata block to {path}")
            return cls.from_text(
                path=path,
                text=new_text,
            )
        except InvalidMetadataFormatException as e:
            # Re-raise with more context about which file failed
            raise InvalidMetadataFormatException(f"Invalid metadata in {path}: {str(e)}")

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
        Get a list of the raw assets that are within this parent folder. These might or
        might not be referenced in the body of the article.

        """
        # Text only notes don't have assets
        if not self.path:
            warning(f"Note {self} has no path; cannot fetch assets.")
            return []

        suffix_whitelist = {".png", ".jpeg", ".jpg"}
        assets = []
        for path in self.path.parent.iterdir():
            if path.suffix in suffix_whitelist:
                assets.append(Asset(self, path))

        # De-duplicate the full images and previews, which are also found by our glob search
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
            image_classes.append("rounded-lg shadow-lg border-4 border-white dark:border-slate-600")

            # Travel specific styling
            if "travel" in self.metadata.tags:
                image_classes.append("large-image")
            else:
                image_classes.append("small-image")

            img["class"] = " ".join(image_classes)

        self._html_content = str(content)
        return self._html_content

    def has_footnotes(self):
        # Find footnote definitions in the text
        return self.text.find("[^") != -1

    def get_preview(self):
        return "\n".join(self.metadata.subtitle)

    @property
    def read_time_minutes(self):
        # https://www.sciencedirect.com/science/article/abs/pii/S0749596X19300786
        WPM = 238
        words = len(self.text.split())
        return (words // WPM) + 1

    @property
    def visible_tag(self):
        # Only show post status during development
        if environ["SCRIBE_ENVIRONMENT"] == "DEVELOPMENT":
            return str(self.metadata.status.value)
        return None
