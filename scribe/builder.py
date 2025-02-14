from collections import defaultdict
from dataclasses import asdict, replace
from hashlib import sha256
from os import getenv
from pathlib import Path
from random import sample
from shutil import copyfile
from sys import exit
from sys import maxsize
import json
from datetime import datetime
from typing import Dict, Optional, Set

from rich.console import Console
from rich.tree import Tree
from click import secho
from jinja2 import Environment, PackageLoader, select_autoescape
from PIL import Image
from PIL.Image import Resampling

from scribe.io import get_asset_path
from scribe.links import local_to_remote_links
from scribe.metadata import BuildMetadata, FeaturedPhotoPosition, NoteStatus
from scribe.models import PageDefinition, PageDirection, TemplateArguments
from scribe.note import Asset, Note
from scribe.parsers import InvalidMetadataException
from scribe.exceptions import HandledBuildError
from scribe.template_utilities import filter_tag, group_by_month


console = Console()


class BuildState:
    """Tracks which files have been built in the current process"""
    
    def __init__(self):
        # Set of files that have been successfully built
        self.built_files: Set[str] = set()
        
    def needs_rebuild(self, file_path: Path) -> bool:
        """Check if a file needs to be rebuilt"""
        return str(file_path) not in self.built_files
        
    def mark_built(self, file_path: Path):
        """Mark a file as successfully built"""
        self.built_files.add(str(file_path))
        
    def clear(self):
        """Clear all build state"""
        self.built_files.clear()


class WebsiteBuilder:
    def __init__(self):
        self.env = Environment(
            loader=PackageLoader(__name__.split(".")[0]), autoescape=select_autoescape()
        )

        self.env.globals["filter_tag"] = filter_tag
        self.env.globals["group_by_month"] = group_by_month
        self.env.globals["FeaturedPhotoPosition"] = FeaturedPhotoPosition
        
        # Initialize build state
        self.build_state = BuildState()

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
                note for note in all_notes if note.metadata.status == NoteStatus.PUBLISHED
            ]

        build_metadata = BuildMetadata()

        # The static build phase will inject the stylesheet hashes that will be used
        # for cache invalidation in subsequent pages
        self.build_static(output_path, build_metadata)

        # Build all notes that are either in draft form or published. Draft notes require a unique
        # URL to access them but should be displayed publically
        self.build_notes(all_notes, output_path, build_metadata)
        self.build_pages(
            [
                PageDefinition("home.html", "index.html", TemplateArguments(notes=published_notes)),
                PageDefinition("rss.xml", "rss.xml", TemplateArguments(notes=published_notes)),
                PageDefinition(
                    "travel.html",
                    "travel.html",
                    TemplateArguments(notes=filter_tag(published_notes, "travel")),
                ),
                PageDefinition(
                    "projects.html",
                    "projects.html",
                ),
                PageDefinition("about.html", "about.html"),
            ],
            output_path,
            build_metadata,
        )

    def build_notes(self, notes: list[Note], output_path: Path, build_metadata: BuildMetadata):
        # Upload the note assets
        for note in notes:
            for asset in note.assets:
                self.process_asset(asset, output_path=output_path)

        # When developing locally it's nice to preview draft notes on the homepage as they will look live
        # But require this as an explicit env variable
        if getenv("SCRIBE_ENVIRONMENT") == "DEVELOPMENT":
            published_notes = notes
        else:
            published_notes = [
                note for note in notes if note.metadata.status == NoteStatus.PUBLISHED
            ]

        # For each tag, sample related posts (up to 3 total)
        notes_by_tag = defaultdict(list)
        for note in published_notes:
            for tag in note.metadata.tags:
                notes_by_tag[tag.lower()].append(note)

        # Build the posts
        post_template_paths = ["post.html", "post-travel.html"]
        post_templates = {path: self.env.get_template(path) for path in post_template_paths}
        for note in notes:
            output_file = output_path / "notes" / f"{note.webpage_path}.html"
            
            # Skip if already built and source hasn't changed
            if not self.build_state.needs_rebuild(note.path):
                secho(f"Skipping {note.title} - already built", fg="green")
                continue
                
            secho(f"Building {note.title}", fg="yellow")
            
            possible_notes = list(
                {
                    candidate_note
                    for tag, all_notes in notes_by_tag.items()
                    for candidate_note in all_notes
                    if tag in note.metadata.tags
                    and candidate_note != note
                    and not note.metadata.external_link
                }
            )
            relevant_notes = sample(possible_notes, min(3, len(possible_notes)))

            # Conditional post template based on tags
            post_template_path = "post.html"
            if "travel" in note.metadata.tags:
                post_template_path = "post-travel.html"
            post_template = post_templates[post_template_path]

            with open(output_file, "w") as file:
                file.write(
                    post_template.render(
                        header=note.title,
                        metadata=note.metadata,
                        content=note.get_html(),
                        has_footnotes=note.has_footnotes(),
                        build_metadata=build_metadata,
                        relevant_notes=relevant_notes,
                    )
                )
            
            # Mark as successfully built
            self.build_state.mark_built(note.path)

    def build_pages(
        self,
        pages: list[PageDefinition],
        output_path: Path,
        build_metadata: BuildMetadata,
    ):
        # Build pages
        for page in pages:
            secho(f"Processing: {page.template} -> {page.url}")

            template = self.env.get_template(page.template)
            page_args = page.page_args or TemplateArguments()
            page_args = self.augment_page_directions(page_args)

            with open(output_path / page.url, "w") as file:
                file.write(template.render(**asdict(page_args), build_metadata=build_metadata))

    def build_rss(self, notes, output_path):
        # Limit to just published notes
        notes = [note for note in notes if note.metadata.status == NoteStatus.PUBLISHED]

        # Build RSS feed
        rss_template = self.env.get_template("rss.xml")
        with open(output_path / "rss.xml", "w") as file:
            file.write(
                rss_template.render(
                    notes=notes,
                )
            )

    def build_static(self, output_path: Path, build_metadata: BuildMetadata):
        # Build static
        static_path = get_asset_path("resources")
        for path in static_path.glob("**/*"):
            if not path.is_file():
                continue
            root_relative = path.relative_to(static_path)
            file_output = output_path / root_relative
            file_output.parent.mkdir(exist_ok=True)
            copyfile(path, file_output)

        # Attempt to locate the built style and code paths
        style_path = static_path / "style.css"
        code_path = static_path / "code.css"
        if style_path.exists():
            build_metadata.style_hash = sha256(style_path.read_text().encode()).hexdigest()
        if code_path.exists():
            build_metadata.code_hash = sha256(code_path.read_text().encode()).hexdigest()

    def get_paginated_arguments(self, notes: list[Note], limit: int):
        for offset in range(0, len(notes), limit):
            yield TemplateArguments(
                notes=notes,
                limit=limit,
                offset=offset,
            )

    def process_asset(self, asset: Asset, output_path: Path):
        # Skip if already processed
        if not self.build_state.needs_rebuild(asset.local_path):
            return
            
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
            
        # Mark as successfully processed
        self.build_state.mark_built(asset.local_path)

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
        directions += [PageDirection("previous", page_index - 1)] if has_previous else []
        directions += [PageDirection("next", page_index + 1)] if has_next else []

        return replace(
            arguments,
            directions=directions,
        )

    def get_notes(self, notes_path: Path):
        notes = []
        found_error = False

        # Create a tree for visual display of notes
        tree = Tree("Current Notes")
        folders: dict[str, Tree] = {}

        for path in notes_path.rglob("*"):
            # Skip hidden directories (those starting with .)
            if any(part.startswith(".") for part in path.parts):
                continue
                
            if path.suffix == ".md":
                try:
                    note = Note.from_file(path)
                    if note.metadata.status in {NoteStatus.DRAFT, NoteStatus.PUBLISHED}:
                        notes.append(note)
                        
                        # Add to the tree visualization
                        relative_path = path.relative_to(notes_path)
                        parent_path = str(relative_path.parent)
                        if parent_path == ".":
                            tree.add(f"[blue]→[/blue] {note.title}")
                        else:
                            if parent_path not in folders:
                                folders[parent_path] = tree.add(f"/{parent_path}")
                            folders[parent_path].add(f"[blue]→[/blue] {note.title}")

                except InvalidMetadataException as e:
                    console.print(f"[red]Invalid metadata: {path}: {e}[/red]")
                    found_error = True

        # Display the tree
        console.print(tree)

        if found_error:
            exit(1)

        # Notes are accessible by both their filename and title
        path_to_remote = {
            alias: f"/notes/{note.webpage_path}"
            for note in notes
            for alias in [note.filename, note.title]
        }

        try:
            for note in notes:
                note.text = local_to_remote_links(note, path_to_remote)
        except HandledBuildError:
            exit(1)

        notes = sorted(notes, key=lambda x: x.metadata.date, reverse=True)

        return notes
