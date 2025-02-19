from asyncio import Semaphore, create_task, gather
from hashlib import md5
from pathlib import Path
from re import finditer, sub
from typing import Set

from rich.console import Console

from scribe.note import Note

console = Console()


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

    if output_path.exists():
        console.print(f"[blue]Skipping {url}, already snapshotted[/blue]")
        return

    async with semaphore:
        try:
            from subprocess import PIPE
            from subprocess import run as subprocess_run

            console.print(f"[yellow]Taking snapshot of {url}[/yellow]")

            # Create the output directory
            output_path.mkdir(parents=True, exist_ok=True)

            cmd = [
                "npx",
                "single-file-cli",
                url,
                str(output_path / "snapshot.html"),
                "--browser-executable-path",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]

            if not headful:
                cmd.extend(["--browser-args", '["--headless=new"]'])

            result = subprocess_run(
                cmd,
                stdout=PIPE,
                stderr=PIPE,
            )

            if result.returncode == 0:
                # The file is already written by single-file-cli
                console.print(f"[green]Successfully snapshotted {url}[/green]")
            else:
                console.print(f"[red]Failed to snapshot {url}: {result.stderr.decode()}[/red]")
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
