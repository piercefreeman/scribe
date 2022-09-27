from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from re import escape as re_escape
from re import finditer, sub
from shutil import copyfile
from sys import maxsize
from typing import Dict, List, Union

from click import secho
from jinja2 import Environment, PackageLoader, select_autoescape
from PIL import Image
from PIL.Image import Resampling

from scribe.io import get_asset_path
from scribe.note import InvalidMetadataException, Note, NoteStatus


def filter_tag(notes: List[Note], tag_values: Union[str, List[str]]):
    """
    Filter for the inclusion/exclusion of some tag. Excluded tags can be prefixed
    with an exclimation point to note that they should be excluded.
    """
    if isinstance(tag_values, str):
        tag_values = [tag_values]

    tag_whitelist = {tag for tag in tag_values if not tag.startswith("!")}
    tag_blacklist = {tag.lstrip("!") for tag in tag_values if tag.startswith("!")}

    if tag_whitelist:
        notes = [
            note
            for note in notes
            if len(set(note.metadata.tags) & set(tag_whitelist)) > 0
        ]
    if tag_blacklist:
        notes = [
            note
            for note in notes
            if len(set(note.metadata.tags) & set(tag_blacklist)) == 0
        ]

    return notes    


@dataclass
class PageDefinition:
    template: str
    url: str


class WebsiteBuilder:
    def __init__(self):
        self.env = Environment(
            loader=PackageLoader(__name__.split(".")[0]),
            autoescape=select_autoescape()
        )

        self.env.globals["filter_tag"] = filter_tag

    def build(self, notes_path: Union[str, Path], output_path: Union[str, Path]):
        notes_path = Path(notes_path).expanduser()

        output_path = Path(output_path).expanduser()

        output_path.mkdir(exist_ok=True)
        (output_path / "notes").mkdir(exist_ok=True)
        (output_path / "images").mkdir(exist_ok=True)

        notes = self.get_notes(notes_path)

        self.build_notes(notes, output_path)
        self.build_pages(
            [
                PageDefinition("home.html", "index.html"),
                PageDefinition("rss.xml", "rss.xml"),
                PageDefinition("notes.html", "notes.html"),
                PageDefinition("travel.html", "travel.html"),
                PageDefinition("about.html", "about.html"),
            ],
            notes,
            output_path
        )
        self.build_static(output_path)

    def build_notes(self, notes: List[Note], output_path):
        # Upload the note assets
        for note in notes:
            for asset in note.assets:
                # Don't process preview files separately, process as part of their main asset package
                # Compress the assets if we don't already have a compressed version
                if not asset.local_preview_path.exists():
                    # The image quality, on a scale from 1 (worst) to 95 (best)
                    image = Image.open(asset.local_path)
                    image.thumbnail([1600, maxsize], Resampling.LANCZOS)
                    #image.save(preview_image_path, "JPEG", quality=95, dpi=(300, 300), subsampling=0)
                    image.save(asset.local_preview_path, quality=95, dpi=(300, 300))

                # Copy the preview image
                # Use a relative path to make sure we place it correctly in the output path
                remote_path = output_path / f"./{asset.remote_preview_path}"
                copyfile(asset.local_preview_path, remote_path)

                # Copy the raw
                remote_path = output_path / f"./{asset.remote_path}"
                copyfile(asset.local_path, remote_path)

        # Build the posts
        post_template = self.env.get_template("post.html")
        for note in notes:
            with open(output_path / "notes" / f"{note.webpage_path}.html", "w") as file:
                file.write(
                    post_template.render(
                        header=note.title,
                        metadata=note.metadata,
                        content=note.get_html()
                    )
                )

    def build_pages(self, pages: List[PageDefinition], notes: List[Note], output_path: Path):
        # Limit to just published notes
        notes = [note for note in notes if note.metadata.status == NoteStatus.PUBLISHED]

        # Build pages
        for page in pages:
            secho(f"Processing: {page}")
            template = self.env.get_template(page.template)
            with open(output_path / page.url, "w") as file:
                file.write(
                    template.render(
                        notes=notes,
                    )
                )

    def build_rss(self, notes, output_path):
        # Limit to just published notes
        notes = [note for note in notes if note.metadata.status == NoteStatus.PUBLISHED]

        # Build RSS feed
        rss_template = self.env.get_template("rss.xml")
        with open(output_path / f"rss.xml", "w") as file:
            file.write(
                rss_template.render(
                    notes=notes,
                )
            )

    def build_static(self, output_path):
        # Build static
        static_path = get_asset_path("resources")
        for path in static_path.glob("**/*"):
            if not path.is_file():
                continue
            root_relative = path.relative_to(static_path)
            file_output = output_path / root_relative
            file_output.parent.mkdir(exist_ok=True)
            copyfile(path, file_output)

    def get_notes(self, notes_path):
        notes = []

        found_error = False
        for path in notes_path.rglob("*"):
            if path.suffix == ".md":
                try:
                    note = Note.from_file(path)
                    if note.metadata.status in {NoteStatus.DRAFT, NoteStatus.PUBLISHED}:
                        notes.append(note)
                except InvalidMetadataException as e:
                    secho(f"Invalid metadata: {path}: {e}", fg="red")
                    found_error = True

        if found_error:
            exit()

        path_to_remote = {
            note.filename: f"/notes/{note.webpage_path}"
            for note in notes
        }

        for note in notes:
            note.text = self.local_to_remote_links(note, path_to_remote)

        notes = sorted(notes, key=lambda x: x.metadata.date, reverse=True)

        return notes

    def local_to_remote_links(
        self,
        note: str,
        path_to_remote: Dict[str, str],
    ) -> str:
        """
        :param path_to_remote: Specify the mapping from the local path (without path prefix)
            and the remote location.
        """
        note_text = note.text

        # Search for links that haven't been escaped with a \ prior to them
        markdown_matches = finditer(r"[^\\]\[(.*?)\]\((.+?)\)", note_text)
        img_matches = finditer(r"<(img).*?src=[\"'](.*?)[\"'].*?/?>", note_text)
        matches = chain(markdown_matches, img_matches)

        local_links = [
            match
            for match in matches
            if not any(
                [
                    "http://" in match.group(2),
                    "https://" in match.group(2),
                    "www." in match.group(2),
                ]
            )
        ]

        # Augment the remote path with links to our media files
        # We choose to use the preview images even if the local paths are pointed
        # to the full quality versions, since this is how we want to render them on first load
        path_to_remote = {
            **path_to_remote,
            **{
                Path(asset.local_path).with_suffix("").name: asset.remote_preview_path
                for asset in note.assets
            },
        }

        # [(text, local link, remote link)]
        to_replace = []

        # Swap the local links
        for match in local_links:
            text = match.group(1)
            local_link = match.group(2)
            
            filename = Path(local_link).with_suffix("").name
            if filename not in path_to_remote:
                raise ValueError(f"Incorrect link {note.filename}, not found locally: {match.group(0)}")
            remote_path = path_to_remote[filename]
            to_replace.append((text, local_link, remote_path))

        # The combination of text & link should be enough to uniquely identify link
        # location and swap with the correct link
        #
        # We can't do this exclusively with local_path because some files may
        # share a common prefix and this will result in incorrect replacement behavior
        for text, local_link, remote_path in to_replace:
            search_text = f"[{text}]({local_link})"
            replace_text = f"[{text}]({remote_path})"
            note_text = note_text.replace(search_text, replace_text)

        # Same replacement logic for raw images
        for text, local_link, remote_path in to_replace:
            note_text = sub(
                f"<img(.*?)src=[\"']{re_escape(local_link)}[\"'](.*?)/?>",
                f"<img\\1src=\"{re_escape(remote_path)}\"\\2/>",
                note_text
            )

        # Treat escape characters specially, since these are used as bash coloring
        note_text = note_text.replace("\\x1b", "\x1b")
        note_text = note_text.replace("\\u001b", "\u001b")

        # Remove other escaped characters unless we are escaping the escape
        note_text = sub(r"([^\\])\\", r"\1", note_text)

        return note_text
