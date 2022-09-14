from pathlib import Path
from shutil import rmtree

from click import Path as ClickPath
from click import command, option, secho

from website_builder.builder import WebsiteBuilder


def build(notes_path, output_path):
    secho("Building new output...", fg="yellow")

    builder = WebsiteBuilder()
    builder.build(notes_path, output_path)

    secho("Website built", fg="green")


@command()
@option("--notes", type=ClickPath(exists=True, dir_okay=True), required=True)
@option("--output", default="static")
def main(notes, output):
    if Path(output).exists():
        secho("Removing previous output...", fg="yellow")
        # When ignore_errors is False, we see an occasional race condition on successive
        # fast saves where we might still be populating this directory before starting to build
        # again. This results in a broken state & crash where we have a mostly empty static
        # directory and the webserver is unable to render the page.
        rmtree(output, ignore_errors=True)
    build(notes, output)
