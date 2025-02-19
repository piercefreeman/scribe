import subprocess
from os import environ, unlink
from pathlib import Path
from shutil import rmtree

from click import (
    Context,
    command,
    option,
    pass_context,
    secho,
)

from scribe.builder import WebsiteBuilder
from scribe.io import get_asset_path


def build(notes_path: str, output_path: str):
    secho("Building new output...", fg="yellow")

    builder = WebsiteBuilder()
    builder.build(notes_path, output_path)

    secho("Website built", fg="green")


@command()
@option("--output", default="static")
@option("--clean", is_flag=True, default=False)
@option("--env", default="PRODUCTION")
@pass_context
def build(ctx: Context, output: str, clean: bool, env: str):
    environ["SCRIBE_ENVIRONMENT"] = env
    secho(f"Environment: {env}")

    notes_path = Path(ctx.obj["notes"]).expanduser().absolute()
    environ["MARKDOWN_PATH"] = str(notes_path)

    # Build the styles
    command = f"cd {get_asset_path('../')} && npm run styles-build"
    response = subprocess.run(command, shell=True)

    # Ensure the styles build was successful
    if response.returncode != 0:
        secho("Styles build failed", fg="red")
        exit(1)

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

    builder.build(notes_path, output)
