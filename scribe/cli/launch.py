from multiprocessing import Process
from os import environ, system
from pathlib import Path
from time import sleep

from click import (
    Path as ClickPath,
    command,
    option,
    secho,
)
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from scribe.cli.runserver import runserver
from scribe.io import get_asset_path


class NotesChangedEventHandler(FileSystemEventHandler):
    def __init__(self, note_path, output_path, env):
        self.scribe_path = get_asset_path("")
        self.note_path = note_path
        self.output_path = output_path
        self.env = env

        self.builder_process = None

    def on_any_event(self, event):
        # TODO: Why is this running twice
        if str(self.scribe_path) in event.src_path:
            secho("website code changed", fg="yellow")
        elif str(self.note_path) in event.src_path and "static" not in event.src_path:
            secho(f"note changed: `{event.src_path}`", fg="yellow")
        else:
            return

        self.build_notes()

    def build_notes(self):
        # Cancel any outdated build requests
        if self.builder_process:
            self.builder_process.terminate()

        self.builder_process = Process(
            target=system,
            args=[
                f"build-notes --notes {self.note_path} --output {self.output_path} --env {self.env}"
            ],
        )
        self.builder_process.start()


@command()
@option("--notes", type=ClickPath(dir_okay=True), required=True)
@option("--output", default="static")
@option("--port", default=3100)
@option("--env", default="DEVELOPMENT")
def main(notes: str, output: str, port: int, env: str):
    # Launch the server
    runserver_process = Process(target=runserver, args=[output, port])
    runserver_process.start()

    environ["MARKDOWN_PATH"] = str(Path(notes).expanduser().absolute())

    # Launch the styling refresh system
    scribe_root = get_asset_path("../").resolve().absolute()
    secho("Using scribe root: " + str(scribe_root), fg="yellow")
    style_process = Process(
        target=system,
        args=[f"cd {scribe_root} && npm run styles-watch"],
    )
    style_process.start()

    event_handler = NotesChangedEventHandler(notes, output, env)

    # Initial run to generate right when the CLI command is run
    event_handler.build_notes()

    observer = Observer()
    observer.schedule(event_handler, ".", recursive=True)
    observer.schedule(event_handler, get_asset_path("templates"), recursive=True)
    observer.start()
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

    runserver_process.join()
    style_process.join()
