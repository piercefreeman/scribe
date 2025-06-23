"""Snapshot plugin for taking snapshots of external URLs found in notes."""

import shutil
from asyncio import Semaphore, create_task, gather, wait_for
from asyncio import TimeoutError as AsyncTimeoutError
from datetime import datetime
from hashlib import md5
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from pydantic import BaseModel
from rich.console import Console

from scribe.context import PageContext
from scribe.logger import get_logger
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import PluginName, SnapshotPluginConfig

if TYPE_CHECKING:
    from scribe.config import ScribeConfig

console = Console()
logger = get_logger(__name__)

MAX_SNAPSHOT_SIZE = 75 * 1024 * 1024


class SnapshotMetadata(BaseModel):
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
        return cls.model_validate_json(path.read_text())

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

    def save_to_file(self, path: Path) -> None:
        """
        Save metadata to a JSON file.
        """
        path.write_text(self.model_dump_json(indent=2))


class SnapshotPlugin(NotePlugin[SnapshotPluginConfig]):
    """
    Plugin to take snapshots of external URLs found in content.

    Required configuration:
    - snapshot_dir: Directory to store snapshots (required)

    Optional configuration:
    - max_concurrent: Max concurrent snapshots (default: 5)
    - max_attempts: Max retry attempts per URL (default: 3)
    - headful: Show browser during snapshots (default: false)
    - enabled: Enable/disable plugin (default: true)
    """

    name = PluginName.SNAPSHOT

    def __init__(
        self, config: SnapshotPluginConfig, global_config: "ScribeConfig | None" = None
    ) -> None:
        super().__init__(config)

        # Get configuration values directly from typed config
        self.output_dir = config.snapshot_dir
        self.snapshots_output_dir = config.snapshots_output_dir
        self.max_concurrent = config.max_concurrent
        self.max_attempts = config.max_attempts
        self.headful = config.headful
        self.enabled = config.enabled

        # Store global config to check environment
        self.global_config = global_config

        # Class-level metadata cache to avoid re-reading files
        self._metadata_cache: dict[str, SnapshotMetadata | None] = {}

    async def process(self, ctx: PageContext) -> PageContext:
        """Process content to find URLs and take snapshots."""
        if not self.enabled:
            return ctx

        # Use traditional approach for backward compatibility with tests
        # The optimization is now in _snapshot_urls which pre-filters cached URLs
        urls = self._extract_urls_from_content(ctx.content)
        if urls:
            await self._snapshot_urls(urls)
            ctx = self._update_links_with_metadata(ctx, urls)

        return ctx

    def _is_production_mode(self) -> bool:
        """Check if we're running in production mode."""
        return (
            self.global_config is not None
            and self.global_config.environment == "production"
        )

    def _extract_urls_from_content(self, content: str) -> set[str]:
        """
        Extract all external URLs from HTML content.

        This method is kept for backward compatibility with tests.
        The optimized version is in _extract_urls_and_update_links.
        """
        soup = BeautifulSoup(content, "html.parser")
        urls = set()

        for link in soup.find_all("a"):
            href = link.get("href")
            if href and self._is_external_url(href):
                urls.add(href)

        return urls

    def _extract_urls_and_update_links(
        self, ctx: PageContext
    ) -> tuple[set[str], PageContext]:
        """
        Extract URLs and update links in a single BeautifulSoup parse to avoid
        double parsing. Returns URLs that need snapshots and updated context.
        """
        soup = BeautifulSoup(ctx.content, "html.parser")
        all_urls = set()
        urls_needing_snapshots = set()

        # Process all links in one pass
        for link in soup.find_all("a"):
            href = link.get("href")
            if href and self._is_external_url(href):
                all_urls.add(href)

                # Check if this URL needs a snapshot
                if self._url_needs_snapshot(href):
                    urls_needing_snapshots.add(href)

                # Update link with metadata if available
                self._update_link_with_metadata(link, href)

        ctx.content = str(soup)
        return urls_needing_snapshots, ctx

    def _get_cached_metadata(self, url: str) -> SnapshotMetadata | None:
        """
        Get metadata for a URL, using cache to avoid repeated disk reads.
        """
        url_hash = self._get_url_hash(url)

        # Check cache first
        if url_hash in self._metadata_cache:
            return self._metadata_cache[url_hash]

        # Load from disk and cache
        metadata_file = self.output_dir / url_hash / "metadata.json"
        if metadata_file.exists():
            try:
                metadata = SnapshotMetadata.from_file(metadata_file)
                self._metadata_cache[url_hash] = metadata
                return metadata
            except Exception as e:
                logger.warning(f"Error reading metadata for {url}: {e}")
                self._metadata_cache[url_hash] = None
                return None
        else:
            self._metadata_cache[url_hash] = None
            return None

    def _url_needs_snapshot(self, url: str) -> bool:
        """
        Check if a URL needs to be snapshotted (not cached successfully).
        This is done synchronously to avoid async overhead for cache hits.
        """
        metadata = self._get_cached_metadata(url)

        if metadata is None:
            # No metadata file exists - needs snapshot
            if self._is_production_mode():
                logger.info(
                    f"Production mode: Skipping crawl for {url} - cached snapshots only"
                )
                return False
            return True

        if metadata.success:
            logger.info(f"Cache HIT: Skipping {url} - already successfully snapshotted")
            return False

        if metadata.too_large:
            logger.info(f"Cache HIT: Skipping {url} - page is too large")
            return False

        if metadata.attempts >= self.max_attempts:
            logger.info(
                f"Cache HIT: Skipping {url} - reached maximum attempts "
                f"({self.max_attempts})"
            )
            return False

        # In production mode, don't attempt new crawls
        if self._is_production_mode():
            logger.info(
                f"Production mode: Skipping crawl for {url} - cached snapshots only"
            )
            return False

        # URL needs retry
        return True

    def _update_link_with_metadata(self, link, url: str) -> None:
        """
        Update a single link element with metadata attributes.
        """
        metadata = self._get_cached_metadata(url)
        if metadata:
            link["data-snapshot-id"] = self._get_url_hash(url)
            for key, value in metadata.to_link_attributes().items():
                link[key] = value

    def _is_external_url(self, url: str) -> bool:
        """
        Check if a URL is external.
        """
        return any(
            [
                "http://" in url,
                "https://" in url,
                "www." in url,
            ]
        )

    def _get_url_hash(self, url: str) -> str:
        """
        Get a consistent hash for a URL.
        """
        return md5(url.encode()).hexdigest()

    async def _snapshot_url(self, url: str, semaphore: Semaphore) -> None:
        """
        Take a snapshot of a single URL using single-file-cli.
        This should only be called for URLs that actually need snapshots.
        """
        url_hash = self._get_url_hash(url)
        output_path = self.output_dir / url_hash
        metadata_file = output_path / "metadata.json"
        snapshot_file = output_path / "snapshot.html"

        # Get cached metadata to check current state
        metadata = self._get_cached_metadata(url)

        # Handle cache hits with appropriate console messages for backward compatibility
        if metadata is not None:
            if metadata.success:
                logger.info(
                    f"Cache HIT: Skipping {url} - already successfully snapshotted"
                )
                return
            if metadata.too_large:
                logger.info(f"Cache HIT: Skipping {url} - page is too large")
                console.print(f"[yellow]Skipping {url} - page is too large[/yellow]")
                return
            if metadata.attempts >= self.max_attempts:
                logger.info(
                    f"Cache HIT: Skipping {url} - reached maximum attempts "
                    f"({self.max_attempts})"
                )
                console.print(
                    f"[red]Skipping {url} - reached maximum attempts "
                    f"({self.max_attempts})[/red]"
                )
                return

        # In production mode, only use cached snapshots - don't attempt new crawls
        if self._is_production_mode():
            logger.info(
                f"Production mode: Skipping crawl for {url} - cached snapshots only"
            )
            console.print(
                f"[blue]Production mode: Skipping crawl for {url} - "
                f"cached snapshots only[/blue]"
            )
            return

        current_attempts = metadata.attempts if metadata else 0

        async with semaphore:
            try:
                from asyncio import create_subprocess_exec
                from asyncio.subprocess import PIPE

                logger.info(
                    f"Cache MISS: Taking snapshot of {url} "
                    f"(attempt {current_attempts + 1}/{self.max_attempts})"
                )
                console.print(
                    f"[yellow]Taking snapshot of {url} "
                    f"(attempt {current_attempts + 1}/{self.max_attempts})[/yellow]"
                )

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

                if not self.headful:
                    cmd.extend(["--browser-args", '["--headless=new"]'])
                else:
                    cmd.extend(["--browser-headless", "false"])

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
                                f"File size ({file_size / 1024 / 1024:.1f}MB) "
                                f"exceeds 75MB limit"
                            )
                            console.print(
                                f"[yellow]Snapshot too large: {error_message}[/yellow]"
                            )
                            snapshot_file.unlink()
                        else:
                            success = True
                            console.print(
                                f"[green]Successfully snapshotted {url}[/green]"
                            )
                    else:
                        error_message = (
                            stderr.decode() or stdout.decode() or "Unknown error"
                        )
                        console.print(
                            f"[red]Failed to snapshot {url}: {error_message}[/red]"
                        )

                except AsyncTimeoutError:
                    error_message = "Process timed out after 75 seconds"
                    console.print(
                        f"[red]Timeout error for {url}: {error_message}[/red]"
                    )
                    try:
                        process.kill()
                    except Exception:
                        pass
                    success = False
                    too_large = False

                new_metadata = SnapshotMetadata(
                    crawled_date=datetime.now(),
                    original_url=url,
                    success=success,
                    attempts=current_attempts + 1,
                    last_error=error_message if not success else None,
                    too_large=too_large,
                )
                new_metadata.save_to_file(metadata_file)

                # Update cache with new metadata
                self._metadata_cache[url_hash] = new_metadata

            except Exception as e:
                error_str = str(e)
                console.print(f"[red]Error snapshotting {url}: {error_str}[/red]")

                new_metadata = SnapshotMetadata(
                    crawled_date=datetime.now(),
                    original_url=url,
                    success=False,
                    attempts=current_attempts + 1,
                    last_error=error_str,
                    too_large=False,
                )
                new_metadata.save_to_file(metadata_file)

                # Update cache with new metadata
                self._metadata_cache[url_hash] = new_metadata

    async def _snapshot_urls(self, urls: set[str]) -> None:
        """
        Take snapshots of multiple URLs concurrently using a semaphore to
        limit concurrent downloads.
        """
        if not urls:
            logger.info("No URLs need snapshots - all cached or skipped")
            return

        # Pre-filter URLs to only include those that actually need snapshots
        # This provides performance optimization while maintaining compatibility
        urls_needing_snapshots = {url for url in urls if self._url_needs_snapshot(url)}

        if not urls_needing_snapshots:
            logger.info("No URLs need snapshots - all cached or skipped")
            return

        semaphore = Semaphore(self.max_concurrent)
        tasks = [
            create_task(self._snapshot_url(url, semaphore))
            for url in urls_needing_snapshots
        ]
        await gather(*tasks)

        console.print("[green]All snapshots completed successfully[/green]")

    def _update_links_with_metadata(
        self, ctx: PageContext, urls: set[str]
    ) -> PageContext:
        """
        Update HTML links with snapshot metadata attributes.
        This method is kept for backward compatibility with tests.
        The optimized version is integrated in _extract_urls_and_update_links.
        """
        soup = BeautifulSoup(ctx.content, "html.parser")

        # Build a dictionary of snapshots for quick lookup
        snapshots = {}
        for url in urls:
            metadata = self._get_cached_metadata(url)
            if metadata:
                snapshots[url] = metadata

        # Update links with snapshot metadata
        for link in soup.find_all("a"):
            href = link.get("href")
            if href and href in snapshots:
                snapshot_metadata = snapshots[href]
                link["data-snapshot-id"] = self._get_url_hash(href)
                for key, value in snapshot_metadata.to_link_attributes().items():
                    link[key] = value

        ctx.content = str(soup)
        return ctx

    def copy_snapshots_to_output(self, output_dir: Path) -> None:
        """Copy successful snapshots to the output directory."""
        if not self.enabled or not self.output_dir.exists():
            return

        snapshots_output_path = output_dir / self.snapshots_output_dir

        # Count successful snapshots for logging
        successful_snapshots = 0

        # Walk through all snapshot directories
        for url_dir in self.output_dir.iterdir():
            if not url_dir.is_dir():
                continue

            metadata_file = url_dir / "metadata.json"
            snapshot_file = url_dir / "snapshot.html"

            # Check if this snapshot was successful
            if metadata_file.exists() and snapshot_file.exists():
                try:
                    metadata = SnapshotMetadata.from_file(metadata_file)
                    if metadata.success:
                        # Create output directory for this snapshot
                        output_snapshot_dir = snapshots_output_path / url_dir.name
                        output_snapshot_dir.mkdir(parents=True, exist_ok=True)

                        # Copy the snapshot file
                        output_snapshot_file = output_snapshot_dir / "snapshot.html"
                        shutil.copy2(snapshot_file, output_snapshot_file)

                        # Copy the metadata file
                        output_metadata_file = output_snapshot_dir / "metadata.json"
                        shutil.copy2(metadata_file, output_metadata_file)

                        successful_snapshots += 1
                        logger.debug(
                            f"Copied snapshot: {url_dir.name} -> {output_snapshot_dir}"
                        )

                except Exception as e:
                    logger.warning(f"Error copying snapshot {url_dir.name}: {e}")

        if successful_snapshots > 0:
            console.print(
                f"[green]Copied {successful_snapshots} snapshots to "
                f"{snapshots_output_path}[/green]"
            )
            logger.info(f"Copied {successful_snapshots} snapshots to output directory")
        else:
            logger.debug("No successful snapshots to copy")
