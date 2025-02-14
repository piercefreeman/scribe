from multiprocessing import Process
from os import environ, system
from pathlib import Path

from click import (
    Path as ClickPath,
)
from click import (
    command,
    option,
    secho,
)
from watchfiles import Change, watch

from scribe.builder import WebsiteBuilder
from scribe.cli.runserver import runserver
from scribe.io import get_asset_path


class NotesBuilder:
    def __init__(self, note_path: str, output_path: str, env: str):
        self.note_path = Path(note_path).expanduser().absolute()
        self.output_path = output_path
        self.env = env
        self.builder = WebsiteBuilder()
        self.scribe_path = get_asset_path("")

        secho(f"Watching notes directory: {self.note_path}", fg="blue")
        secho(f"Watching scribe path: {self.scribe_path}", fg="blue")

    def handle_changes(self, changes):
        rebuild_needed = False
        changed_files = set()

        for change_type, path in changes:
            path = Path(path)
            secho(f"\nChange detected: {change_type.name} - {path}", fg="blue")

            # Skip temporary and backup files
            if path.name.endswith(".tmp") or ".scribe_backups" in str(path):
                secho("Skipping temporary/backup file", fg="blue")
                continue

            # Handle website code changes
            if str(self.scribe_path) in str(path):
                secho("Website code changed", fg="yellow")
                rebuild_needed = True
                # Clear all build state for website code changes
                self.builder.build_state.clear()
                continue

            # Handle note changes
            try:
                # Check if the file is under the notes directory
                path.relative_to(self.note_path)

                if path.suffix == ".md":
                    if change_type in {Change.added, Change.modified}:
                        secho(f"Note changed: {path.relative_to(self.note_path)}", fg="yellow")
                        rebuild_needed = True
                        # Track which files need to be rebuilt
                        changed_files.add(path)
                    else:
                        secho(f"Ignoring change type: {change_type.name}", fg="blue")
                else:
                    secho(f"Ignoring non-markdown file: {path.suffix}", fg="blue")
            except ValueError:
                secho(f"Ignoring file outside notes directory: {path}", fg="blue")

        if rebuild_needed:
            # Clear changed files from build state before rebuilding
            for file in changed_files:
                self.builder.build_state.built_files.discard(str(file))
            self.build()

    def build(self):
        environ["SCRIBE_ENVIRONMENT"] = self.env
        environ["MARKDOWN_PATH"] = str(self.note_path)

        secho("\nRebuilding...", fg="yellow")
        self.builder.build(self.note_path, self.output_path)
        secho("Done.", fg="green")


@command()
@option("--notes", type=ClickPath(dir_okay=True), required=True)
@option("--output", default="static")
@option("--port", default=3100)
@option("--env", default="DEVELOPMENT")
def main(notes: str, output: str, port: int, env: str):
    notes_path = Path(notes).expanduser().absolute()
    secho(f"Starting server with notes from: {notes_path}", fg="green")

    # Launch the server
    runserver_process = Process(target=runserver, args=[output, port])
    runserver_process.start()

    environ["MARKDOWN_PATH"] = str(notes_path)

    # Launch the styling refresh system
    scribe_root = get_asset_path("../").resolve().absolute()
    secho(f"Using scribe root: {scribe_root}", fg="blue")
    style_process = Process(
        target=system,
        args=[f"cd {scribe_root} && npm run styles-watch"],
    )
    style_process.start()

    builder = NotesBuilder(notes, output, env)

    # Initial build
    builder.build()

    secho("\nWatching for changes... (Press Ctrl+C to stop)", fg="green")

    try:
        # Watch for changes with a debounce of 50ms to avoid duplicate events
        for changes in watch(
            notes_path, get_asset_path("templates"), watch_filter=None, debounce=50
        ):
            builder.handle_changes(changes)
    except KeyboardInterrupt:
        pass

    runserver_process.join()
    style_process.join()
