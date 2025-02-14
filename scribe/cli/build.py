import subprocess
from os import environ, unlink
from pathlib import Path
from shutil import rmtree

from click import (
    Path as ClickPath,
)
from click import (
    command,
    option,
    secho,
)

from scribe.builder import WebsiteBuilder
from scribe.io import get_asset_path


def build(notes_path, output_path):
    secho("Building new output...", fg="yellow")

    builder = WebsiteBuilder()
    builder.build(notes_path, output_path)

    secho("Website built", fg="green")


@command()
@option("--notes", type=ClickPath(exists=True, dir_okay=True), required=True)
@option("--output", default="static")
@option("--clean", is_flag=True, default=False)
@option("--env", default="PRODUCTION")
def main(notes: str, output: str, clean: bool, env: str):
    environ["SCRIBE_ENVIRONMENT"] = env
    secho(f"Environment: {env}")

    environ["MARKDOWN_PATH"] = str(Path(notes).expanduser().absolute())

    # Build the styles
    command = f"cd {get_asset_path('../')} && npm run styles-build"
    subprocess.run(command, shell=True)

    builder = WebsiteBuilder()
    if clean:
        if Path(output).exists():
            secho("Removing all previous output...", fg="yellow")
            # When ignore_errors is False, we see an occasional race condition on successive
            # fast saves where we might still be populating this directory before starting to build
            # again. This results in a broken state & crash where we have a mostly empty static
            # directory and the webserver is unable to render the page.
            rmtree(output, ignore_errors=True)
            # Clear build state to force rebuild of everything
            builder.build_state.clear()
    else:
        # Just delete the html files, keep the media
        if Path(output).exists():
            secho("Removing previous html output...", fg="yellow")
            for item in Path(output).glob("**/*.html"):
                unlink(item)

    builder.build(notes, output)
