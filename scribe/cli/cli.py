from click import Context, group, option, pass_context
from click import Path as ClickPath

from scribe.cli.build import build
from scribe.cli.format import format
from scribe.cli.snapshot import snapshot_links
from scribe.cli.write import start_writing


@group()
@option("--notes", type=ClickPath(exists=True, dir_okay=True), required=True)
@pass_context
def main(ctx: Context, notes: str):
    """Main CLI entrypoint for Scribe."""
    ctx.obj = {"notes": notes}


main.add_command(format)
main.add_command(start_writing)
main.add_command(build)
main.add_command(snapshot_links)
