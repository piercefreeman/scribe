from pathlib import Path

from click import Context, command, pass_context
from rich.console import Console
from rich.table import Table

from scribe.builder import WebsiteBuilder
from scribe.snapshot import SnapshotMetadata, extract_urls_from_note, get_url_hash

console = Console()


@command()
@pass_context
def snapshot_validate(ctx: Context):
    """Validate that all external links in notes have corresponding snapshots."""
    notes_path = Path(ctx.obj["notes"]).expanduser()
    snapshots_path = notes_path / "snapshots"

    if not snapshots_path.exists():
        console.print("[red]No snapshots directory found. Run `snapshot-links` first.[/red]")
        return

    # Get all notes
    builder = WebsiteBuilder()
    notes = builder.get_notes(notes_path)

    # Track statistics
    total_urls = 0
    missing_snapshots = []
    failed_snapshots = []
    too_large_snapshots = []

    # Create a table for the report
    table = Table(title="Snapshot Validation Report")
    table.add_column("Note", style="cyan")
    table.add_column("URL", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Details", style="red")

    # Check each note for external URLs
    for note in notes:
        urls = extract_urls_from_note(note)
        if not urls:
            continue

        total_urls += len(urls)
        for url in urls:
            url_hash = get_url_hash(url)
            snapshot_dir = snapshots_path / url_hash
            metadata_file = snapshot_dir / "metadata.json"
            snapshot_file = snapshot_dir / "snapshot.html"

            if not snapshot_dir.exists() or not metadata_file.exists():
                missing_snapshots.append((note, url))
                table.add_row(
                    note.title,
                    url,
                    "Missing",
                    "No snapshot directory or metadata file",
                )
                continue

            metadata = SnapshotMetadata.from_file(metadata_file)

            if metadata.too_large:
                too_large_snapshots.append((note, url))
                table.add_row(
                    note.title,
                    url,
                    "Too Large",
                    f"File exceeds size limit ({metadata.last_error})",
                )
            elif not metadata.success:
                failed_snapshots.append((note, url))
                table.add_row(
                    note.title,
                    url,
                    "Failed",
                    metadata.last_error or "Unknown error",
                )
            elif not snapshot_file.exists():
                failed_snapshots.append((note, url))
                table.add_row(
                    note.title,
                    url,
                    "Failed",
                    "Snapshot file missing despite successful metadata",
                )

    # Print the report
    console.print()
    if total_urls == 0:
        console.print("[yellow]No external URLs found in notes.[/yellow]")
        return

    console.print(table)
    console.print()

    # Print summary
    successful = (
        total_urls - len(missing_snapshots) - len(failed_snapshots) - len(too_large_snapshots)
    )
    console.print(f"[blue]Total URLs found:[/blue] {total_urls}")
    console.print(f"[green]Successful snapshots:[/green] {successful}")

    if missing_snapshots:
        console.print(f"[red]Missing snapshots:[/red] {len(missing_snapshots)}")
    if failed_snapshots:
        console.print(f"[red]Failed snapshots:[/red] {len(failed_snapshots)}")
    if too_large_snapshots:
        console.print(f"[yellow]Too large snapshots:[/yellow] {len(too_large_snapshots)}")

    # Exit with error if any snapshots are missing. We allow failed snapshots because
    # they might be caused by pages that simply won't resolve.
    if missing_snapshots:
        exit(1)
