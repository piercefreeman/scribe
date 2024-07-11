from logging import warning
from os import environ
from pathlib import Path
from re import sub

from bs4 import BeautifulSoup
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.extensions.tables import TableExtension

from scribe.metadata import FeaturedPhotoPayload, NoteMetadata
from scribe.parsers import (
    get_raw_text,
    get_simple_content,
    parse_metadata,
    parse_title,
)


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

    filename: str | None = None
    path: Path | None = None

    def __init__(
        self,
        text: str,
        title: str,
        metadata: NoteMetadata,
        simple_content: str,
        filename: str | None = None,
        path: str | Path | None = None,
    ):
        self.text = text
        self.title = title
        self.metadata = metadata
        self.simple_content = simple_content
        self.filename = filename
        self.path = Path(path) if path else None

    @classmethod
    def from_file(cls, path: Path):
        with open(path) as file:
            text = file.read().strip()
            return cls.from_text(
                path=path,
                text=text,
            )

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

    def get_html(self):
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
            image_classes.append(
                "rounded-lg shadow-lg border-4 border-white dark:border-slate-600"
            )

            # Travel specific styling
            # TODO: Generalize
            if "travel" in self.metadata.tags:
                image_classes.append(
                    "lg:max-w-[100vw] lg:-ml-[125px] lg:w-offset-content-image-lg"
                )
                image_classes.append("xl:-ml-[250px] xl:w-offset-content-image-xl")

            img["class"] = " ".join(image_classes)

        return str(content)

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
