from dataclasses import asdict, replace
from os import getenv
from pathlib import Path
from shutil import copyfile
from sys import maxsize

from click import secho
from jinja2 import Environment, PackageLoader, select_autoescape
from PIL import Image
from PIL.Image import Resampling

from scribe.io import get_asset_path
from scribe.links import local_to_remote_links
from scribe.metadata import FeaturedPhotoPosition, NoteStatus
from scribe.models import PageDefinition, PageDirection, TemplateArguments
from scribe.note import Asset, Note
from scribe.parsers import InvalidMetadataException
from scribe.template_utilities import filter_tag, group_by_month


class WebsiteBuilder:
    def __init__(self):
        self.env = Environment(
            loader=PackageLoader(__name__.split(".")[0]), autoescape=select_autoescape()
        )

        self.env.globals["filter_tag"] = filter_tag
        self.env.globals["group_by_month"] = group_by_month
        self.env.globals["FeaturedPhotoPosition"] = FeaturedPhotoPosition

    def build(self, notes_path: str | Path, output_path: str | Path):
        notes_path = Path(notes_path).expanduser()

        output_path = Path(output_path).expanduser()

        output_path.mkdir(exist_ok=True)
        (output_path / "notes").mkdir(exist_ok=True)
        (output_path / "images").mkdir(exist_ok=True)

        all_notes = self.get_notes(notes_path)
        # When developing locally it's nice to preview draft notes on the homepage as they will look live
        # But require this as an explicit env variable
        if getenv("SCRIBE_ENVIRONMENT") == "DEVELOPMENT":
            published_notes = all_notes
        else:
            published_notes = [
                note
                for note in all_notes
                if note.metadata.status == NoteStatus.PUBLISHED
            ]

        # Build all notes that are either in draft form or published. Draft notes require a unique
        # URL to access them but should be displayed publically
        self.build_notes(all_notes, output_path)
        self.build_pages(
            [
                PageDefinition(
                    "home.html", "index.html", TemplateArguments(notes=published_notes)
                ),
                PageDefinition(
                    "rss.xml", "rss.xml", TemplateArguments(notes=published_notes)
                ),
                PageDefinition(
                    "travel.html",
                    "travel.html",
                    TemplateArguments(notes=filter_tag(published_notes, "travel")),
                ),
                PageDefinition("about.html", "about.html"),
            ],
            output_path,
        )
        self.build_static(output_path)

    def build_notes(self, notes: list[Note], output_path: Path):
        # Upload the note assets
        for note in notes:
            for asset in note.assets:
                self.process_asset(asset, output_path=output_path)

        # Build the posts
        post_template_paths = ["post.html", "post-travel.html"]
        post_templates = {
            path: self.env.get_template(path) for path in post_template_paths
        }
        for note in notes:
            # Conditional post template based on tags
            post_template_path = "post.html"
            if "travel" in note.metadata.tags:
                post_template_path = "post-travel.html"
            post_template = post_templates[post_template_path]

            with open(output_path / "notes" / f"{note.webpage_path}.html", "w") as file:
                file.write(
                    post_template.render(
                        header=note.title,
                        metadata=note.metadata,
                        content=note.get_html(),
                        has_footnotes=note.has_footnotes(),
                    )
                )

    def build_pages(self, pages: list[PageDefinition], output_path: Path):
        # Build pages
        for page in pages:
            secho(f"Processing: {page.template} -> {page.url}")

            template = self.env.get_template(page.template)
            page_args = page.page_args or TemplateArguments()
            page_args = self.augment_page_directions(page_args)

            with open(output_path / page.url, "w") as file:
                file.write(template.render(**asdict(page_args)))

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

    def get_paginated_arguments(self, notes: list[Note], limit: int):
        for offset in range(0, len(notes), limit):
            yield TemplateArguments(
                notes=notes,
                limit=limit,
                offset=offset,
            )

    def process_asset(self, asset: Asset, output_path: Path):
        # Don't process preview files separately, process as part of their main asset package
        # Compress the assets if we don't already have a compressed version
        if not asset.local_preview_path.exists():
            # The image quality, on a scale from 1 (worst) to 95 (best)
            image = Image.open(asset.local_path)
            # image.thumbnail((1600, maxsize), Resampling.LANCZOS)
            image.thumbnail((3200, maxsize), Resampling.LANCZOS)
            # image.save(preview_image_path, "JPEG", quality=95, dpi=(300, 300), subsampling=0)
            image.save(
                asset.local_preview_path,
                quality=95,
                dpi=(300, 300),
                subsampling=2,  # Corresponds to 4:2:0
                progressive=True,
            )

        # Copy the preview image
        # Use a relative path to make sure we place it correctly in the output path
        remote_path = output_path / f"./{asset.remote_preview_path}"
        if not remote_path.exists():
            copyfile(asset.local_preview_path, remote_path)

        # Copy the raw
        remote_path = output_path / f"./{asset.remote_path}"
        if not remote_path.exists():
            copyfile(asset.local_path, remote_path)

    def augment_page_directions(self, arguments: TemplateArguments):
        """
        Use the metadata in a TemplateArgument to determine if there are additional
        pages in the sequence.

        """
        if arguments.offset is None or arguments.limit is None:
            return arguments

        note_count = len(arguments.notes) if arguments.notes else 0

        page_index = arguments.offset // arguments.limit
        has_next = arguments.offset + arguments.limit < note_count
        has_previous = page_index > 0

        directions = []
        directions += (
            [PageDirection("previous", page_index - 1)] if has_previous else []
        )
        directions += [PageDirection("next", page_index + 1)] if has_next else []

        return replace(
            arguments,
            directions=directions,
        )

    def get_notes(self, notes_path: Path):
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
            note.filename: f"/notes/{note.webpage_path}" for note in notes
        }

        for note in notes:
            note.text = local_to_remote_links(note, path_to_remote)

        notes = sorted(notes, key=lambda x: x.metadata.date, reverse=True)

        return notes
