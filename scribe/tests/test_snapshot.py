import traceback
from os import chdir
from pathlib import Path

import pytest
from click.testing import CliRunner
from rich.console import Console

from scribe.cli.snapshot import snapshot_links
from scribe.note import Note
from scribe.snapshot import extract_urls_from_note

console = Console()


def test_extract_urls():
    """Test that we correctly extract external URLs but not image links."""
    text = """# Test Note

meta:
    date: November 12, 2024
    status: publish
    subtitle:
        - Test subtitle
    tags:
        - test

Here are some links:
- [External Link](https://example.com)
- [Another Link](http://test.com)
- [Local Link](./local.md)
- [WWW Link](www.google.com)

And some images that should be ignored:
![Image](https://example.com/image.jpg)
<img src="https://example.com/another.jpg" />

More links:
- [Mixed](https://example.com/path?q=test)
- [Escaped Link](https://example.com/\\[escaped\\])
"""

    note = Note.from_text(text=text, path="/fake-path.md")
    urls = extract_urls_from_note(note)

    # Should find all external links but not images
    assert urls == {
        "https://example.com",
        "http://test.com",
        "www.google.com",
        "https://example.com/path?q=test",
        "https://example.com/[escaped]",
    }


@pytest.mark.integration
@pytest.mark.parametrize("headful", [True, False])
def test_snapshot_example(tmp_path: Path, headful: bool):
    """Test that we can successfully snapshot example.com."""
    text = """# Test Note

meta:
    date: November 12, 2024
    status: publish
    subtitle:
        - Test subtitle
    tags:
        - test

[Example](https://example.com)
"""

    # Create test directory structure
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    note_path = notes_dir / "test.md"
    note_path.write_text(text)

    # Snapshots will be created inside the notes directory
    snapshots_dir = notes_dir / "snapshots"

    # Change to the temp directory for the test
    original_dir = Path.cwd()
    chdir(tmp_path)

    try:
        runner = CliRunner()
        console.print("[yellow]Test paths:[/yellow]")
        console.print(f"[blue]Current directory:[/blue] {Path.cwd()}")
        console.print(f"[blue]Notes directory:[/blue] {notes_dir}")
        console.print(f"[blue]Snapshots directory:[/blue] {snapshots_dir}")

        result = runner.invoke(
            snapshot_links,
            ["--snapshots", "snapshots"] + (["--headful"] if headful else []),
            obj={"notes": str(notes_dir)},
            catch_exceptions=False,
        )

        console.print("[yellow]Command output:[/yellow]")
        console.print(result.output)

        if result.exception:
            console.print("[red]Command exception:[/red]")
            console.print(result.exception)
            if result.exc_info:
                console.print("[red]Traceback:[/red]")
                console.print("".join(traceback.format_tb(result.exc_info[2])))

        assert result.exit_code == 0

        # Verify snapshot was created
        from scribe.snapshot import get_url_hash

        snapshot_path = snapshots_dir / get_url_hash("https://example.com") / "snapshot.html"
        console.print(f"[blue]Looking for snapshot at:[/blue] {snapshot_path}")

        if not snapshot_path.exists():
            # List contents of snapshots directory if it exists
            if snapshots_dir.exists():
                console.print(f"[yellow]Contents of {snapshots_dir}:[/yellow]")
                for path in snapshots_dir.rglob("*"):
                    console.print(f"[blue]Found:[/blue] {path}")
                    if path.is_file():
                        console.print("[green]File contents:[/green]")
                        console.print(path.read_text())
            else:
                console.print(f"[red]Snapshots directory does not exist: {snapshots_dir}[/red]")

            # List contents of current directory
            console.print("[yellow]Contents of current directory:[/yellow]")
            for path in Path.cwd().rglob("*"):
                console.print(f"[blue]Found:[/blue] {path}")

        assert snapshot_path.exists()

        # Basic check that we got HTML content
        content = snapshot_path.read_text()
        assert "<html" in content.lower()
        assert "<body" in content.lower()
        assert "example domain" in content.lower()

        # Verify metadata.json exists and has correct format
        metadata_path = snapshots_dir / get_url_hash("https://example.com") / "metadata.json"
        assert metadata_path.exists()

        import json

        metadata = json.loads(metadata_path.read_text())
        assert "crawled_date" in metadata
        assert "original_url" in metadata
        assert metadata["original_url"] == "https://example.com"

        # Verify crawled_date is a valid ISO format date
        from datetime import datetime

        datetime.fromisoformat(metadata["crawled_date"])
    finally:
        # Always restore the original directory
        chdir(original_dir)
