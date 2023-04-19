from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from pathlib import Path
from re import findall, sub
from typing import Any, List, Optional, Union

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.extensions.tables import TableExtension
from pydantic import BaseModel, ValidationError, validator
from yaml import safe_load as yaml_loads


@unique
class NoteStatus(Enum):
    SCRATCH = "SCRATCH"
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


@dataclass
class ParsedPayload:
    """
    Defines a value payload that has been successfully parsed by lexers

    """
    result: Any
    parsed_lines: List[int]


class InvalidMetadataException(Exception):
    def __init__(self, message):
        self.message = message


class NoteMetadata(BaseModel):
    """
    Defines the post metadata that shouldn't be directly visible but drives different
    elements of the note creation engine.

    """
    class Config:
        extra = "forbid"

    date: str | datetime
    tags: List[str] = []
    #status: NoteStatus = NoteStatus.SCRATCH
    # TODO: Fix the typing here
    status: Any = NoteStatus.SCRATCH
    subtitle: List[str] = []

    # URLs in addition to the system-given URLs
    # This is primarily useful to keep backwards compatibility with
    # posts that change over time
    # urls: List[str] = []

    # Featured photos are paths to photos that should be featured in photo sections
    # They can be separate from those that are contained in the body of the post
    featured_photos: List[str] = []

    @validator("date")
    def validate_date(cls, date):
        return date_parser.parse(date)

    @validator("status")
    def validate_status(cls, status):
        if status == "draft":
            return NoteStatus.DRAFT
        elif status == "publish":
            return NoteStatus.PUBLISHED
        else:
            raise ValueError(f"Unknown status: `{status}`")


class Asset:
    """
    Assets are tied to their parent note. This class normalizes assets
    to be the full quality image. In other words we'll convert preview links
    to their full filepath, following our assumed path patterns.

    """
    def __init__(self, note: "Note", path: Path):
        self.root_path = note.webpage_path
        self.path = Path(str(path).replace("-preview", "")).absolute()

    @property
    def name(self):
        return Path(self.path).with_suffix("").name

    @property
    def preview_name(self):
        return self.name + "-preview"

    @property
    def local_path(self):
        return self.path

    @property
    def local_preview_path(self):
        return self.path.parent / f"{self.preview_name}{self.path.suffix}"

    @property
    def remote_path(self):
        return f"/images/{self.root_path}-{self.name}{self.path.suffix}"

    @property
    def remote_preview_path(self):
        return f"/images/{self.root_path}-{self.preview_name}{self.path.suffix}"

    def __hash__(self):
        return hash(self.path)


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

    filename: Optional[str] = None
    path: Optional[str] = None

    def __init__(self, path: Union[Path, str], text: str):
        parsed_title = self.parse_title(text)
        parsed_metadata = self.parse_metadata(text)

        self.text = self.get_raw_text(text, [parsed_title, parsed_metadata])
        self.title = parsed_title.result
        self.metadata = parsed_metadata.result

        self.path = Path(path)
        self.filename = self.path.with_suffix("").name

        self.simple_content = self.get_simple_content(self.text)

    @classmethod
    def from_file(cls, path: Path):
        with open(path) as file:
            text = file.read().strip()
            return cls(
                path=path,
                text=text,
            )

    def parse_title(self, text: str) -> Optional[ParsedPayload]:
        """
        Determine if the first line is a header

        """
        first_line = text.strip().split("\n")[0]
        headers = findall(r"(#+)(.*)", first_line)
        headers = sorted(headers, key=lambda x: len(x[0]))
        if not headers:
            raise InvalidMetadataException("No header specified.")
        return ParsedPayload(headers[0][1].strip(), [0])

    def parse_metadata(self, text: str) -> ParsedPayload:
        metadata_string = ""
        meta_started = False
        parsed_lines = []
        for i, line in enumerate(text.split("\n")):
            # Start read with the meta: tag indication that we have
            # started to declare the dictionary, end it otherwise.
            if line.strip() == "meta:":
                meta_started = True
            if line.strip() == "":
                meta_started = False
            if meta_started:
                metadata_string += f"{line}\n"
                parsed_lines.append(i)

        if not metadata_string:
            # If users haven't specified metadata, assume it is a scratch note
            return ParsedPayload(NoteMetadata(date=datetime.now().isoformat()), [])

        try:
            metadata = NoteMetadata.parse_obj(yaml_loads(metadata_string)["meta"])
        except ValidationError as e:
            raise InvalidMetadataException(str(e))

        return ParsedPayload(metadata, parsed_lines)

    def get_raw_text(self, text, parsed_payloads: List[ParsedPayload]) -> str:
        ignore_lines = {
            line
            for parsed in parsed_payloads
            for line in parsed.parsed_lines
        }

        text = "\n".join(
            [
                line
                for i, line in enumerate(text.split("\n"))
                if i not in ignore_lines
            ]
        ).strip()

        # Normalize image patterns to ![]()
        # Different markdown implementations have different patterns for this
        text = sub(r"!\[\[(.*)\]\]", r"![](\1)", text)

        return text

    def get_simple_content(self, text: str):
        html = markdown(text.split("\n")[0])
        content = ''.join(BeautifulSoup(html, "html.parser").findAll(text=True))
        return sub(r"\s", " ", content)

    @property
    def assets(self) -> List[Asset]:
        """
        Get a list of the raw assets that are within this parent folder. These might or
        might not be referenced in the body of the article.

        """
        suffix_whitelist = {".png", ".jpeg", ".jpg"}
        assets = []
        for path in Path(self.path).parent.iterdir():
            if path.suffix in suffix_whitelist:
                assets.append(Asset(self, path))
        # De-duplicate the full images and previews, which are also found by our glob search
        return list(set(assets))

    @property
    def featured_assets(self) -> List[Asset]:
        """
        List of assets that should be featured on photo collages.
        """
        assets = []
        for relative_path in self.metadata.featured_photos:
            full_path = Path(self.path).parent / relative_path
            if not full_path.exists():
                raise ValueError(f"Unknown path: {full_path}")
            assets.append(Asset(self, full_path))
        # De-duplicate the full images and previews, which are also found by our glob search
        return assets

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

    def get_html(self):
        html = markdown(
            self.text,
            extensions=[
                CodeHiliteExtension(use_pygments=True),
                FencedCodeExtension(),
                FootnoteExtension(BACKLINK_TEXT="↢"),
                TableExtension(),
            ]
        )

        content = BeautifulSoup(html, "html.parser")

        # Style images - these should be located somewhere in the html dom (like in a template
        # tag - so tailwind can pick up on them)
        for img in content.find_all("img"):
            img["class"] = " ".join([*img.get("class", []), "rounded-sm"])

        return str(content)

    @property
    def read_time_minutes(self):
        # https://www.sciencedirect.com/science/article/abs/pii/S0749596X19300786
        WPM = 238
        words = len(self.text.split())
        return (words // WPM) + 1
