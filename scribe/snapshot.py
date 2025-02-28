import json
from asyncio import Semaphore, create_task, gather, wait_for
from asyncio import TimeoutError as AsyncTimeoutError
from dataclasses import dataclass
from datetime import datetime
from hashlib import md5
from pathlib import Path
from re import finditer, sub
from typing import Set

from rich.console import Console

from scribe.note import Note

console = Console()

MAX_SNAPSHOT_SIZE = 75 * 1024 * 1024


@dataclass
class SnapshotMetadata:
    """
    Metadata for a webpage snapshot.
    """

    crawled_date: datetime
    original_url: str
    success: bool
    attempts: int
    last_error: str | None
    too_large: bool = False

    @classmethod
    def from_file(cls, path: Path) -> "SnapshotMetadata":
        """
        Load metadata from a JSON file.
        """
        data = json.loads(path.read_text())
        return cls(
            crawled_date=datetime.fromisoformat(data["crawled_date"]),
            original_url=data["original_url"],
            success=data.get("success", False),
            attempts=data.get("attempts", 0),
            last_error=data.get("last_error"),
            too_large=data.get("too_large", False),
        )

    def to_link_attributes(self) -> dict[str, str]:
        """
        Convert metadata to HTML link attributes.
        Only returns attributes if the snapshot was successful.
        """
        if not self.success and not self.too_large:
            return {}

        return {
            "data-snapshot-date": self.crawled_date.isoformat(),
            "data-snapshot-url": self.original_url,
        }

    def to_dict(self) -> dict:
        """
        Convert metadata to a dictionary for JSON serialization.
        """
        return {
            "crawled_date": self.crawled_date.isoformat(),
            "original_url": self.original_url,
            "success": self.success,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "too_large": self.too_large,
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
    url: str, output_dir: Path, semaphore: Semaphore, headful: bool = False, max_attempts: int = 3
) -> None:
    """
    Take a snapshot of a single URL using single-file-cli.

    Args:
        url: The URL to snapshot
        output_dir: Directory to save the snapshot
        semaphore: Semaphore to limit concurrent downloads
        headful: Whether to show the browser window during snapshot
        max_attempts: Maximum number of attempts to snapshot the URL
    """
    url_hash = get_url_hash(url)
    output_path = output_dir / url_hash
    metadata_file = output_path / "metadata.json"
    snapshot_file = output_path / "snapshot.html"

    # Load existing metadata if it exists
    current_attempts = 0
    if metadata_file.exists():
        metadata = SnapshotMetadata.from_file(metadata_file)
        if metadata.success:
            console.print(f"[blue]Skipping {url} - already successfully snapshotted[/blue]")
            return
        if metadata.too_large:
            console.print(f"[yellow]Skipping {url} - page is too large[/yellow]")
            return
        current_attempts = metadata.attempts
        if current_attempts >= max_attempts:
            console.print(f"[red]Skipping {url} - reached maximum attempts ({max_attempts})[/red]")
            return

    async with semaphore:
        try:
            from asyncio import create_subprocess_exec
            from asyncio.subprocess import PIPE

            console.print(
                f"[yellow]Taking snapshot of {url} (attempt {current_attempts + 1}/{max_attempts})[/yellow]"
            )

            # Create the output directory
            output_path.mkdir(parents=True, exist_ok=True)

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

            try:
                stdout, stderr = await wait_for(process.communicate(), timeout=75)
                success = False
                error_message = None
                too_large = False

                if process.returncode == 0 and snapshot_file.exists():
                    file_size = snapshot_file.stat().st_size
                    if file_size > MAX_SNAPSHOT_SIZE:
                        success = False
                        too_large = True
                        error_message = (
                            f"File size ({file_size / 1024 / 1024:.1f}MB) exceeds 45MB limit"
                        )
                        console.print(f"[yellow]Snapshot too large: {error_message}[/yellow]")
                        # Delete the large file
                        snapshot_file.unlink()
                    else:
                        success = True
                        console.print(f"[green]Successfully snapshotted {url}[/green]")
                else:
                    error_message = stderr.decode() or stdout.decode() or "Unknown error"
                    console.print(f"[red]Failed to snapshot {url}: {error_message}[/red]")

            except AsyncTimeoutError:
                error_message = "Process timed out after 75 seconds"
                console.print(f"[red]Timeout error for {url}: {error_message}[/red]")
                try:
                    process.kill()
                except Exception:
                    pass
                success = False
                too_large = False

            # Save metadata
            metadata = SnapshotMetadata(
                crawled_date=datetime.now(),
                original_url=url,
                success=success,
                attempts=current_attempts + 1,
                last_error=error_message if not success else None,
                too_large=too_large,
            )
            metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        except Exception as e:
            error_str = str(e)
            console.print(f"[red]Error snapshotting {url}: {error_str}[/red]")

            # Save metadata for the failed attempt
            metadata = SnapshotMetadata(
                crawled_date=datetime.now(),
                original_url=url,
                success=False,
                attempts=current_attempts + 1,
                last_error=error_str,
                too_large=False,
            )
            metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))


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
