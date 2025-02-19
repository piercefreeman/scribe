import json
from asyncio import Semaphore, create_task, gather
from dataclasses import dataclass
from datetime import datetime
from hashlib import md5
from pathlib import Path
from re import finditer, sub
from typing import Set

from rich.console import Console

from scribe.note import Note

console = Console()


@dataclass
class SnapshotMetadata:
    """
    Metadata for a webpage snapshot.
    """

    crawled_date: datetime
    original_url: str

    @classmethod
    def from_file(cls, path: Path) -> "SnapshotMetadata":
        """
        Load metadata from a JSON file.
        """
        data = json.loads(path.read_text())
        return cls(
            crawled_date=datetime.fromisoformat(data["crawled_date"]),
            original_url=data["original_url"],
        )

    def to_link_attributes(self) -> dict[str, str]:
        """
        Convert metadata to HTML link attributes.
        """
        return {
            "data-snapshot-date": self.crawled_date.isoformat(),
            "data-snapshot-url": self.original_url,
        }


def extract_urls_from_note(note: Note) -> Set[str]:
    """
    Extract all external URLs from a note's markdown content.

    Args:
        note: The note to extract URLs from

    Returns:
        Set of unique URLs found in the note
    """
    # Search for markdown links that haven't been escaped
    markdown_matches = finditer(r"(?<!!)(?<!\\)\[(.*?)\]\((.+?)\)", note.text)

    urls = {
        sub(r"\\(.)", r"\1", match.group(2))  # Remove escape characters
        for match in markdown_matches
        if any(
            [
                "http://" in match.group(2),
                "https://" in match.group(2),
                "www." in match.group(2),
            ]
        )
    }

    return urls


def get_url_hash(url: str) -> str:
    """
    Get a consistent hash for a URL.

    Args:
        url: The URL to hash

    Returns:
        MD5 hash of the URL
    """
    return md5(url.encode()).hexdigest()


async def snapshot_url(
    url: str, output_dir: Path, semaphore: Semaphore, headful: bool = False
) -> None:
    """
    Take a snapshot of a single URL using single-file-cli.

    Args:
        url: The URL to snapshot
        output_dir: Directory to save the snapshot
        semaphore: Semaphore to limit concurrent downloads
        headful: Whether to show the browser window during snapshot
    """
    url_hash = get_url_hash(url)
    output_path = output_dir / url_hash

    # Until we have a valid metadata file, we consider the URL as not snapshotted. This lets
    # us try failed requests again.
    if (output_path / "metadata.json").exists():
        console.print(f"[blue]Skipping {url} - already snapshotted[/blue]")
        console.print(f" - Metadata: {output_path / 'metadata.json'}")
        return

    async with semaphore:
        try:
            from asyncio import create_subprocess_exec
            from asyncio.subprocess import PIPE

            console.print(f"[yellow]Taking snapshot of {url}[/yellow]")

            # Create the output directory
            output_path.mkdir(parents=True, exist_ok=True)

            # Create the full path for the snapshot file
            snapshot_file = output_path / "snapshot.html"
            metadata_file = output_path / "metadata.json"

            cmd = [
                "npx",
                "single-file-cli",
                url,
                str(snapshot_file),
                "--browser-executable-path",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "--browser-load-max-time",
                str(15 * 1000),
            ]

            if not headful:
                cmd.extend(["--browser-args", '["--headless=new"]'])
            else:
                cmd.extend(["--browser-headless", "false"])

            console.print(f"[yellow]Running command: {' '.join(cmd)}[/yellow]")

            process = await create_subprocess_exec(
                *cmd,
                stdout=PIPE,
                stderr=PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # Verify the file was created
                if snapshot_file.exists():
                    # Save metadata
                    metadata = {"crawled_date": datetime.now().isoformat(), "original_url": url}
                    metadata_file.write_text(json.dumps(metadata, indent=2))

                    console.print(f"[green]Successfully snapshotted {url}[/green]")
                else:
                    console.print(f"[red]Failed to snapshot {url}: File not created[/red]")
                    console.print(f"[red]stderr: {stderr.decode()}[/red]")
                    console.print(f"[red]stdout: {stdout.decode()}[/red]")
            else:
                console.print(f"[red]Failed to snapshot {url}: {stderr.decode()}[/red]")
                console.print(f"[red]stdout: {stdout.decode()}[/red]")
        except Exception as e:
            console.print(f"[red]Error snapshotting {url}: {str(e)}[/red]")


async def snapshot_urls(
    urls: Set[str], output_dir: Path, headful: bool = False, max_concurrent: int = 5
) -> None:
    """
    Take snapshots of multiple URLs concurrently using a semaphore to limit concurrent downloads.

    Args:
        urls: Set of URLs to snapshot
        output_dir: Directory to save snapshots
        headful: Whether to show the browser window during snapshot
        max_concurrent: Maximum number of concurrent downloads
    """
    semaphore = Semaphore(max_concurrent)
    tasks = [create_task(snapshot_url(url, output_dir, semaphore, headful)) for url in urls]
    await gather(*tasks)

    console.print("[green]All snapshots completed successfully[/green]")
