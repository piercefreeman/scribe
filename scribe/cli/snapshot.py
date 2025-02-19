from asyncio import run
from pathlib import Path

from click import Context, command, option, pass_context
from rich.console import Console

from scribe.builder import WebsiteBuilder
from scribe.snapshot import extract_urls_from_note, snapshot_urls

console = Console()


@command()
@option("--snapshots", default="snapshots", help="Directory to store webpage snapshots")
@option(
    "--headful",
    is_flag=True,
    default=False,
    help="Show browser window during snapshot (useful for debugging)",
)
@pass_context
def snapshot_links(ctx: Context, snapshots: str, headful: bool):
    """Take snapshots of all external links found in markdown notes."""
    notes_path = Path(ctx.obj["notes"]).expanduser()
    snapshots_path = Path(snapshots).expanduser()

    # Get all notes
    builder = WebsiteBuilder()
    notes = builder.get_notes(notes_path)

    # Extract all unique URLs from notes
    all_urls = set()
    for note in notes:
        urls = extract_urls_from_note(note)
        if urls:
            console.print(f"[yellow]Found {len(urls)} URLs in {note.title}[/yellow]")
            all_urls.update(urls)

    if not all_urls:
        console.print("[yellow]No external URLs found in notes[/yellow]")
        return

    console.print(f"[green]Found {len(all_urls)} unique URLs to snapshot[/green]")

    # Take snapshots of URLs concurrently
    run(snapshot_urls(all_urls, snapshots_path, headful=headful))
