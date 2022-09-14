from multiprocessing import Process
from os import system
from time import sleep

from click import Path as ClickPath
from click import command, option, secho
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from website_builder.cli.runserver import runserver
from website_builder.io import get_asset_path


class NotesChangedEventHandler(FileSystemEventHandler):
    def __init__(self, note_path, output_path):
        self.website_builder_path = get_asset_path("")
        self.note_path = note_path
        self.output_path = output_path

        self.builder_process = None

    def on_any_event(self, event):
        # TODO: Why is this running twice
        if str(self.website_builder_path) in event.src_path:
            secho("website code changed", fg="yellow")
        elif str(self.note_path) in event.src_path:
            secho("note changed", fg="yellow")
        else:
            return

        # Cancel any outdated build requests
        if self.builder_process:
            self.builder_process.terminate()

        self.builder_process = Process(target=system, args=[f"build-notes --notes {self.note_path} --output {self.output_path}"])
        self.builder_process.start()


@command()
@option("--notes", type=ClickPath(dir_okay=True), required=True)
@option("--output", default="static")
@option("--port", default=3100)
def main(notes, output, port):
    # Launch the server
    runserver_process = Process(target=runserver, args=[output, port])
    runserver_process.start()

    # Launch the styling refresh system
    style_process = Process(target=system, args=[f"cd {get_asset_path('../')} && npx tailwindcss -o {get_asset_path('resources/style.css')} --watch"])
    style_process.start()

    event_handler = NotesChangedEventHandler(notes, output)

    observer = Observer()
    observer.schedule(event_handler, ".", recursive=True)
    observer.start()
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

    runserver_process.join()
    style_process.join()
