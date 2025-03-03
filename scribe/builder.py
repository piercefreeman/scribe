from collections import defaultdict
from dataclasses import asdict, replace
from hashlib import sha256
from os import getenv
from pathlib import Path
from random import sample
from shutil import copy2, copyfile
from sys import exit, maxsize
from typing import Set

from bs4 import BeautifulSoup
from click import secho
from jinja2 import Environment, PackageLoader, select_autoescape
from PIL import Image
from PIL.Image import Resampling
from rich.console import Console
from rich.tree import Tree

from scribe.asset import WEB_DPI
from scribe.exceptions import HandledBuildError
from scribe.io import get_asset_path
from scribe.links import local_to_remote_links
from scribe.logging import LOGGER
from scribe.metadata import BuildMetadata, FeaturedPhotoPosition, NoteStatus
from scribe.models import PageDefinition, PageDirection, TemplateArguments
from scribe.note import Asset, Note
from scribe.parsers import InvalidMetadataError
from scribe.snapshot import SnapshotMetadata, get_url_hash
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

    def build(self, notes_path: str | Path, output_path: str | Path) -> None:
        """
        Build the website from markdown notes.

        Args:
            notes_path: Path to the notes directory
            output_path: Path to the output directory
        """
        try:
            notes_path = Path(notes_path).expanduser()
            output_path = Path(output_path).expanduser()
            snapshots_dir = notes_path / "snapshots"

            output_path.mkdir(exist_ok=True)

            # Get all notes
            notes = self.get_notes(notes_path)
            if not notes:
                secho("No notes found", fg="yellow")
                return

            # Sort notes by date
            processed_notes = sorted(notes, key=lambda x: x.metadata.date, reverse=True)

            build_metadata = BuildMetadata()

            # The static build phase will inject the stylesheet hashes that will be used
            # for cache invalidation in subsequent pages
            console.print("[blue]Building static assets[/blue]")
            self.build_static(output_path, build_metadata)

            # Add snapshot metadata to the note html
            console.print("[blue]Building note text[/blue]")
            processed_notes = self.process_links(processed_notes)
            processed_notes = self.process_snapshots(processed_notes, snapshots_dir, output_path)
            processed_notes = self.process_assets(processed_notes, output_path)

            # When developing locally it's nice to preview draft notes on the homepage as they will look live
            # But require this as an explicit env variable
            if getenv("SCRIBE_ENVIRONMENT") == "DEVELOPMENT":
                published_notes = processed_notes
            else:
                published_notes = [
                    note for note in processed_notes if note.metadata.status == NoteStatus.PUBLISHED
                ]

            # Build all notes that are either in draft form or published. Draft notes require a unique
            # URL to access them but should be displayed publically
            console.print("[blue]Building notes[/blue]")
            self.build_notes(processed_notes, output_path, build_metadata)

            console.print("[blue]Building pages[/blue]")
            self.build_pages(
                [
                    PageDefinition(
                        "home.html", "index.html", TemplateArguments(notes=published_notes)
                    ),
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

        except Exception as e:
            console.print(f"[red]Build failed:[/red] {str(e)}")
            raise HandledBuildError() from e

    def build_notes(self, notes: list[Note], output_path: Path, build_metadata: BuildMetadata):
        # When developing locally it's nice to preview draft notes on the homepage as they will look live
        # But require this as an explicit env variable
        if getenv("SCRIBE_ENVIRONMENT") == "DEVELOPMENT":
            published_notes = notes
        else:
            published_notes = [
                note for note in notes if note.metadata.status == NoteStatus.PUBLISHED
            ]

        # Pre-build the notes directory
        notes_path = output_path / "notes"
        notes_path.mkdir(exist_ok=True)
        assets_path = output_path / "images"
        assets_path.mkdir(exist_ok=True)

        # For each tag, sample related posts (up to 3 total)
        notes_by_tag = defaultdict(list)
        for note in published_notes:
            for tag in note.metadata.tags:
                notes_by_tag[tag.lower()].append(note)

        # Build the posts
        post_template_paths = ["post.html", "post-travel.html"]
        post_templates = {path: self.env.get_template(path) for path in post_template_paths}
        for note in notes:
            output_file = notes_path / f"{note.webpage_path}.html"

            # Skip if already built and source hasn't changed
            if not note.path:
                console.print(f"[yellow]Skipping {note.title} due to missing path[/yellow]")
                continue

            if not self.build_state.needs_rebuild(note.path):
                continue

            console.print(f"[yellow]Building {note.title}[/yellow]")

            possible_note_paths = list(
                {
                    candidate_note.path
                    for tag, all_notes in notes_by_tag.items()
                    for candidate_note in all_notes
                    if tag in note.metadata.tags
                    and candidate_note != note
                    and not note.metadata.external_link
                }
            )
            possible_notes = [note for note in published_notes if note.path in possible_note_paths]
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
                        content=note.html_content,
                        has_footnotes=note.has_footnotes(),
                        build_metadata=build_metadata,
                        relevant_notes=relevant_notes,
                    )
                )

            # Mark as successfully built
            if note.path is not None:
                self.build_state.mark_built(note.path)

    def process_snapshots(self, notes: list[Note], snapshots_dir: Path, output_path: Path):
        # Process each note
        processed_notes: list[Note] = []
        for note in notes:
            try:
                # Process snapshots if they exist
                html_content = (
                    self._handle_snapshot(note.html_content, snapshots_dir, output_path)
                    if snapshots_dir.exists()
                    else note.html_content
                )

                new_note = note.model_copy(update={"html_content": html_content})

                # Save the processed note with the modified HTML
                processed_notes.append(new_note)
            except InvalidMetadataError as e:
                console.print(f"[red]Invalid metadata in {note.path}:[/red] {str(e)}")
                exit(1)
            except Exception as e:
                console.print(f"[red]Error processing {note.path}:[/red] {str(e)}")
                raise HandledBuildError() from e

        return processed_notes

    def process_links(self, notes: list[Note]):
        # Notes are accessible by both their filename and title
        path_to_remote = {
            alias: f"/notes/{note.webpage_path}"
            for note in notes
            for alias in [note.filename, note.title]
        }

        # Process each note's links, skipping those with broken links
        processed_notes: list[Note] = []
        found_error = False
        for note in notes:
            try:
                new_note = note.model_copy(
                    update={"text": local_to_remote_links(note, path_to_remote)}
                )
                processed_notes.append(new_note)
            except HandledBuildError:
                console.print(f"[yellow]Skipping {note.title} due to broken links[/yellow]")
                found_error = True
                continue

        if found_error:
            console.print(
                "[yellow]Some notes were skipped due to errors. Fix the issues and rebuild to include them.[/yellow]"
            )

        return processed_notes

    def process_assets(self, notes: list[Note], output_path: Path):
        processed_notes: list[Note] = []

        for note in notes:
            processed_assets: list[Asset] = []

            for asset in note.assets:
                LOGGER.info(f"\nProcessing asset: {asset.local_path}")
                LOGGER.info(f"Output path: {output_path}")

                # Skip if already processed
                if not self.build_state.needs_rebuild(asset.local_path):
                    LOGGER.info(f"Asset already processed: {asset.local_path}")
                    processed_assets.append(asset)
                    continue

                # Create resolution map based on DPI
                with Image.open(asset.local_path) as img:
                    dpi = img.info.get("dpi", (WEB_DPI, WEB_DPI))[0]  # Get horizontal DPI

                    resolution_map = {}
                    if dpi > WEB_DPI:
                        # Round DPI to nearest integer to avoid float key issues
                        dpi_int = round(dpi)
                        resolution_map = {WEB_DPI: "1x", dpi_int: f"{dpi_int / WEB_DPI:.1f}x"}

                    # Update the asset with the resolution map
                    asset = asset.model_copy(update={"resolution_map": resolution_map})
                    LOGGER.info(f"Asset resolution map: {asset.resolution_map}")

                # Ensure the cache directory exists
                asset.cache_dir.mkdir(parents=True, exist_ok=True)

                # Don't process preview files separately, process as part of their main asset package
                # Compress the assets if we don't already have a compressed version
                if not asset.local_preview_path.exists():
                    # Create preview image - always at standard DPI
                    image = Image.open(asset.local_path)
                    image.thumbnail((3200, maxsize), Resampling.LANCZOS)
                    image.save(
                        asset.local_preview_path,
                        quality=95,
                        dpi=(72, 72),  # Always save preview at standard DPI
                        subsampling=2,  # Corresponds to 4:2:0
                        progressive=True,
                    )
                    LOGGER.info("Preview image created successfully")

                # Create DPI variants based on the resolution map
                for dpi in asset.resolution_map.keys():
                    dpi_path = asset.get_dpi_path(dpi)
                    if not dpi_path.exists():
                        image = Image.open(asset.local_path)
                        image.save(
                            dpi_path,
                            quality=95,
                            dpi=(dpi, dpi),
                            subsampling=2,
                            progressive=True,
                        )
                        LOGGER.info(f"{dpi} DPI version created successfully")

                # Copy the preview image
                remote_path = output_path / f"./{asset.remote_preview_path}"
                remote_path.parent.mkdir(parents=True, exist_ok=True)
                if not remote_path.exists():
                    copyfile(asset.local_preview_path, remote_path)

                # Copy the raw
                remote_path = output_path / f"./{asset.remote_path}"
                remote_path.parent.mkdir(parents=True, exist_ok=True)
                if not remote_path.exists():
                    copyfile(asset.local_path, remote_path)

                # Copy DPI variants if they exist
                for dpi in asset.resolution_map.keys():
                    local_dpi_path = asset.get_dpi_path(dpi)
                    if local_dpi_path.exists():
                        remote_dpi_path = output_path / f"./{asset.get_remote_dpi_path(dpi)}"
                        remote_dpi_path.parent.mkdir(parents=True, exist_ok=True)
                        if not remote_dpi_path.exists():
                            copyfile(local_dpi_path, remote_dpi_path)

                # Mark as successfully processed
                self.build_state.mark_built(asset.local_path)
                processed_assets.append(asset)
                LOGGER.info(f"Asset processing complete: {asset.local_path}\n")

            # Update the note with the processed assets
            new_note = note.model_copy(update={"assets": processed_assets})
            processed_notes.append(new_note)

        return processed_notes

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
            page_args = self._augment_page_directions(page_args)

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

    def get_notes(self, notes_path: Path) -> list[Note]:
        notes: list[Note] = []
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

                except InvalidMetadataError as e:
                    console.print(f"[red]Invalid metadata: {path}: {e}[/red]")
                    found_error = True

        # Display the tree
        console.print(tree)

        if found_error:
            exit(1)

        return notes

    def _augment_page_directions(self, arguments: TemplateArguments):
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

    def _handle_snapshot(self, html_content: str, snapshots_dir: Path, output_dir: Path) -> str:
        """
        Process HTML content to:
        1. Find all external links
        2. Check if we have snapshots for them
        3. Add snapshot-id and metadata attributes to links that have snapshots
        4. Copy snapshot HTML files to the output directory

        Args:
            html_content: The HTML content to process
            snapshots_dir: Directory containing snapshots
            output_dir: Build output directory

        Returns:
            Modified HTML content with snapshot attributes added
        """
        soup = BeautifulSoup(html_content, "html.parser")
        snapshot_output_dir = output_dir / "snapshots"
        snapshot_output_dir.mkdir(exist_ok=True)

        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Skip relative links
            if not any(href.startswith(prefix) for prefix in ["http://", "https://", "www."]):
                continue

            snapshot_id = get_url_hash(href)
            snapshot_dir = snapshots_dir / snapshot_id

            if snapshot_dir.exists():
                # Load metadata
                metadata_file = snapshot_dir / "metadata.json"
                if metadata_file.exists():
                    try:
                        metadata = SnapshotMetadata.from_file(metadata_file)

                        # Add snapshot-id and metadata attributes to the link
                        link["snapshot-id"] = snapshot_id
                        for key, value in metadata.to_link_attributes().items():
                            link[key] = value

                        # Copy only the HTML snapshot if it hasn't been copied yet
                        source_html = snapshot_dir / "snapshot.html"
                        target_dir = snapshot_output_dir / snapshot_id
                        target_html = target_dir / "snapshot.html"

                        if source_html.exists() and not target_html.exists():
                            target_dir.mkdir(exist_ok=True)
                            copy2(source_html, target_html)
                            console.print(f"[green]Copied snapshot for {href}[/green]")
                    except Exception as e:
                        console.print(
                            f"[red]Error processing snapshot metadata for {href}: {str(e)}[/red]"
                        )

        return str(soup)
