from pathlib import Path

from click import Context, command, pass_context
from rich.console import Console

from scribe.backup import backup_file
from scribe.footnotes import FootnoteParser

console = Console()


@command()
@pass_context
def format(ctx: Context):
    """
    Reorder footnotes in all markdown files to be sequential based on appearance.

    """
    notes_path = Path(ctx.obj["notes"]).expanduser()

    # Process each markdown file
    for path in notes_path.rglob("*.md"):
        # Skip files in backup directories
        if ".scribe_backups" in str(path):
            continue

        try:
            with open(path) as file:
                text = file.read()

            # Skip files without footnotes
            if not FootnoteParser.has_footnotes(text):
                continue

            console.print(f"[yellow]Processing {path.relative_to(notes_path)}[/yellow]")

            # Create backup before modifying
            backup_file(path)

            # Reorder footnotes
            new_text = FootnoteParser.reorder(text)

            # Only write if changes were made
            if new_text != text:
                with open(path, "w") as file:
                    file.write(new_text)
                console.print(f"[green]Updated footnotes in {path.relative_to(notes_path)}[/green]")
            else:
                console.print(f"[blue]No changes needed for {path.relative_to(notes_path)}[/blue]")

        except Exception as e:
            console.print(f"[red]Error processing {path}: {str(e)}[/red]")
            continue
