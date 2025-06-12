"""Tests for the snapshot plugin."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from scribe.context import PageContext
from scribe.note_plugins.config import SnapshotPluginConfig
from scribe.note_plugins.snapshot import SnapshotMetadata, SnapshotPlugin


class TestSnapshotMetadata:
    """Test cases for the SnapshotMetadata class."""

    def test_metadata_creation(self):
        """Test creating SnapshotMetadata instance."""
        metadata = SnapshotMetadata(
            crawled_date=datetime(2023, 1, 1, 12, 0, 0),
            original_url="https://example.com",
            success=True,
            attempts=1,
            last_error=None,
        )

        assert metadata.crawled_date == datetime(2023, 1, 1, 12, 0, 0)
        assert metadata.original_url == "https://example.com"
        assert metadata.success is True
        assert metadata.attempts == 1
        assert metadata.last_error is None
        assert metadata.too_large is False

    def test_metadata_from_file(self, tmp_path):
        """Test loading metadata from JSON file."""
        metadata_file = tmp_path / "metadata.json"
        data = {
            "crawled_date": "2023-01-01T12:00:00",
            "original_url": "https://example.com",
            "success": True,
            "attempts": 1,
            "last_error": None,
            "too_large": False,
        }
        metadata_file.write_text(json.dumps(data))

        metadata = SnapshotMetadata.from_file(metadata_file)

        assert metadata.crawled_date == datetime(2023, 1, 1, 12, 0, 0)
        assert metadata.original_url == "https://example.com"
        assert metadata.success is True

    def test_to_link_attributes_success(self):
        """Test converting successful metadata to link attributes."""
        metadata = SnapshotMetadata(
            crawled_date=datetime(2023, 1, 1, 12, 0, 0),
            original_url="https://example.com",
            success=True,
            attempts=1,
            last_error=None,
        )

        attrs = metadata.to_link_attributes()

        assert attrs["data-snapshot-date"] == "2023-01-01T12:00:00"
        assert attrs["data-snapshot-url"] == "https://example.com"

    def test_to_link_attributes_failure(self):
        """Test that failed snapshots don't return attributes."""
        metadata = SnapshotMetadata(
            crawled_date=datetime(2023, 1, 1, 12, 0, 0),
            original_url="https://example.com",
            success=False,
            attempts=3,
            last_error="Timeout",
        )

        attrs = metadata.to_link_attributes()

        assert attrs == {}

    def test_to_link_attributes_too_large(self):
        """Test that too-large snapshots return attributes."""
        metadata = SnapshotMetadata(
            crawled_date=datetime(2023, 1, 1, 12, 0, 0),
            original_url="https://example.com",
            success=False,
            attempts=1,
            last_error="Too large",
            too_large=True,
        )

        attrs = metadata.to_link_attributes()

        assert attrs["data-snapshot-date"] == "2023-01-01T12:00:00"
        assert attrs["data-snapshot-url"] == "https://example.com"

    def test_model_dump(self):
        """Test converting metadata to dictionary."""
        metadata = SnapshotMetadata(
            crawled_date=datetime(2023, 1, 1, 12, 0, 0),
            original_url="https://example.com",
            success=True,
            attempts=1,
            last_error=None,
        )

        result = metadata.model_dump()

        expected = {
            "crawled_date": datetime(2023, 1, 1, 12, 0, 0),
            "original_url": "https://example.com",
            "success": True,
            "attempts": 1,
            "last_error": None,
            "too_large": False,
        }
        assert result == expected


class TestSnapshotPlugin:
    """Test cases for the SnapshotPlugin."""

    @pytest.fixture
    def plugin(self, tmp_path):
        """Create a SnapshotPlugin instance for testing."""
        config = SnapshotPluginConfig(
            snapshot_dir=str(tmp_path / "snapshots"),
            max_concurrent=2,
            max_attempts=2,
            headful=False,
            enabled=True,
        )
        return SnapshotPlugin(config)

    @pytest.fixture
    def disabled_plugin(self, tmp_path):
        """Create a disabled SnapshotPlugin instance."""
        config = SnapshotPluginConfig(
            snapshot_dir=str(tmp_path / "snapshots"),
            enabled=False,
        )
        return SnapshotPlugin(config)

    @pytest.fixture
    def base_context(self):
        """Create a base PageContext for testing."""
        return PageContext(
            source_path=Path("test.md"),
            relative_path=Path("test.md"),
            output_path=Path("test.html"),
            raw_content="",
            content="",
        )

    def test_plugin_initialization_missing_snapshot_dir(self):
        """Test plugin initialization fails without snapshot_dir."""
        with pytest.raises(ValueError, match="Field required"):
            SnapshotPluginConfig()

    def test_plugin_initialization_with_required_config(self, tmp_path):
        """Test plugin initialization with required snapshot_dir."""
        config = SnapshotPluginConfig(snapshot_dir=str(tmp_path / "test_snapshots"))
        plugin = SnapshotPlugin(config)

        assert plugin.output_dir == Path(tmp_path / "test_snapshots")
        assert plugin.max_concurrent == 5
        assert plugin.max_attempts == 3
        assert plugin.headful is False
        assert plugin.enabled is True

    def test_plugin_initialization_custom_config(self, tmp_path):
        """Test plugin initialization with custom config."""
        config = SnapshotPluginConfig(
            snapshot_dir="/custom/path",
            max_concurrent=10,
            max_attempts=5,
            headful=True,
            enabled=False,
        )
        plugin = SnapshotPlugin(config)

        assert plugin.output_dir == Path("/custom/path")
        assert plugin.max_concurrent == 10
        assert plugin.max_attempts == 5
        assert plugin.headful is True
        assert plugin.enabled is False

    async def test_disabled_plugin_passthrough(self, disabled_plugin, base_context):
        """Test that disabled plugin passes through content unchanged."""
        content = "Check out [this link](https://example.com) for more info."
        base_context.content = content

        result = await disabled_plugin.process(base_context)

        assert result.content == content

    def test_extract_urls_from_content(self, plugin):
        """Test URL extraction from HTML content."""
        content = """
        <p>Check out <a href="https://example.com">this link</a> and
        <a href="http://test.org">another</a>.
        Also see <a href="./local.html">local link</a> and
        <a href="www.github.com">www link</a>.
        <img src="https://image.com/pic.jpg" alt="Image"> should be ignored.</p>
        """

        urls = plugin._extract_urls_from_content(content)

        expected_urls = {
            "https://example.com",
            "http://test.org",
            "www.github.com",
        }
        assert urls == expected_urls

    def test_extract_urls_empty_content(self, plugin):
        """Test URL extraction from empty content."""
        urls = plugin._extract_urls_from_content("")
        assert urls == set()

    def test_extract_urls_no_links(self, plugin):
        """Test URL extraction from content with no links."""
        content = "This is just plain text with no links."
        urls = plugin._extract_urls_from_content(content)
        assert urls == set()

    def test_get_url_hash(self, plugin):
        """Test URL hashing."""
        url = "https://example.com"
        hash1 = plugin._get_url_hash(url)
        hash2 = plugin._get_url_hash(url)

        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hash length
        assert hash1 != plugin._get_url_hash("https://different.com")

    @patch("asyncio.create_subprocess_exec")
    async def test_snapshot_url_success(self, mock_subprocess, plugin, tmp_path):
        """Test successful URL snapshot."""
        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"success", b"")
        mock_subprocess.return_value = mock_process

        # Create snapshot file to simulate success
        url = "https://example.com"
        url_hash = plugin._get_url_hash(url)
        snapshot_dir = plugin.output_dir / url_hash
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = snapshot_dir / "snapshot.html"
        snapshot_file.write_text("<html>test</html>")

        from asyncio import Semaphore

        semaphore = Semaphore(1)

        with patch("scribe.note_plugins.snapshot.console"):
            await plugin._snapshot_url(url, semaphore)

        # Check metadata was created
        metadata_file = snapshot_dir / "metadata.json"
        assert metadata_file.exists()

        metadata = SnapshotMetadata.from_file(metadata_file)
        assert metadata.success is True
        assert metadata.original_url == url
        assert metadata.attempts == 1

    @patch("asyncio.create_subprocess_exec")
    async def test_snapshot_url_failure(self, mock_subprocess, plugin, tmp_path):
        """Test failed URL snapshot."""
        # Mock subprocess failure
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Error occurred")
        mock_subprocess.return_value = mock_process

        url = "https://example.com"
        from asyncio import Semaphore

        semaphore = Semaphore(1)

        with patch("scribe.note_plugins.snapshot.console"):
            await plugin._snapshot_url(url, semaphore)

        # Check metadata was created
        url_hash = plugin._get_url_hash(url)
        metadata_file = plugin.output_dir / url_hash / "metadata.json"
        assert metadata_file.exists()

        metadata = SnapshotMetadata.from_file(metadata_file)
        assert metadata.success is False
        assert metadata.last_error == "Error occurred"
        assert metadata.attempts == 1

    @patch("asyncio.create_subprocess_exec")
    async def test_snapshot_url_too_large(self, mock_subprocess, plugin, tmp_path):
        """Test snapshot that's too large."""
        # Mock subprocess success
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"success", b"")
        mock_subprocess.return_value = mock_process

        # Create large snapshot file
        url = "https://example.com"
        url_hash = plugin._get_url_hash(url)
        snapshot_dir = plugin.output_dir / url_hash
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = snapshot_dir / "snapshot.html"

        # Create file larger than MAX_SNAPSHOT_SIZE
        large_content = "x" * (76 * 1024 * 1024)  # 76MB
        snapshot_file.write_text(large_content)

        from asyncio import Semaphore

        semaphore = Semaphore(1)

        with patch("scribe.note_plugins.snapshot.console"):
            await plugin._snapshot_url(url, semaphore)

        # File should be deleted
        assert not snapshot_file.exists()

        # Check metadata
        metadata_file = snapshot_dir / "metadata.json"
        assert metadata_file.exists()

        metadata = SnapshotMetadata.from_file(metadata_file)
        assert metadata.success is False
        assert metadata.too_large is True
        assert "exceeds 75MB limit" in metadata.last_error

    async def test_snapshot_url_skip_existing_success(self, plugin, tmp_path):
        """Test skipping URL that already has successful snapshot."""
        url = "https://example.com"
        url_hash = plugin._get_url_hash(url)
        snapshot_dir = plugin.output_dir / url_hash
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Create existing successful metadata
        metadata = SnapshotMetadata(
            crawled_date=datetime.now(),
            original_url=url,
            success=True,
            attempts=1,
            last_error=None,
        )
        metadata_file = snapshot_dir / "metadata.json"
        metadata.save_to_file(metadata_file)

        from asyncio import Semaphore

        semaphore = Semaphore(1)

        with patch("scribe.note_plugins.snapshot.console"):
            await plugin._snapshot_url(url, semaphore)

    async def test_snapshot_url_skip_too_large(self, plugin, tmp_path):
        """Test skipping URL that was previously too large."""
        url = "https://example.com"
        url_hash = plugin._get_url_hash(url)
        snapshot_dir = plugin.output_dir / url_hash
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Create existing too-large metadata
        metadata = SnapshotMetadata(
            crawled_date=datetime.now(),
            original_url=url,
            success=False,
            attempts=1,
            last_error="Too large",
            too_large=True,
        )
        metadata_file = snapshot_dir / "metadata.json"
        metadata.save_to_file(metadata_file)

        from asyncio import Semaphore

        semaphore = Semaphore(1)

        with patch("scribe.note_plugins.snapshot.console") as mock_console:
            await plugin._snapshot_url(url, semaphore)

        mock_console.print.assert_called_with(
            f"[yellow]Skipping {url} - page is too large[/yellow]"
        )

    async def test_snapshot_url_skip_max_attempts(self, plugin, tmp_path):
        """Test skipping URL that has reached max attempts."""
        url = "https://example.com"
        url_hash = plugin._get_url_hash(url)
        snapshot_dir = plugin.output_dir / url_hash
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Create existing failed metadata with max attempts
        metadata = SnapshotMetadata(
            crawled_date=datetime.now(),
            original_url=url,
            success=False,
            attempts=plugin.max_attempts,
            last_error="Failed",
        )
        metadata_file = snapshot_dir / "metadata.json"
        metadata.save_to_file(metadata_file)

        from asyncio import Semaphore

        semaphore = Semaphore(1)

        with patch("scribe.note_plugins.snapshot.console") as mock_console:
            await plugin._snapshot_url(url, semaphore)

        mock_console.print.assert_called_with(
            f"[red]Skipping {url} - reached maximum attempts "
            f"({plugin.max_attempts})[/red]"
        )

    async def test_snapshot_urls(self, plugin):
        """Test snapshotting multiple URLs."""
        urls = {"https://example.com", "https://test.org"}

        # Mock the _snapshot_url method instead
        with patch.object(
            plugin, "_snapshot_url", new_callable=AsyncMock
        ) as mock_snapshot_url:
            with patch("scribe.note_plugins.snapshot.console"):
                await plugin._snapshot_urls(urls)

        # Should call _snapshot_url for each URL
        assert mock_snapshot_url.call_count == len(urls)

    def test_update_links_with_metadata(self, plugin, tmp_path):
        """Test updating HTML links with snapshot metadata."""
        # Create test metadata
        url = "https://example.com"
        url_hash = plugin._get_url_hash(url)
        snapshot_dir = plugin.output_dir / url_hash
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        metadata = SnapshotMetadata(
            crawled_date=datetime(2023, 1, 1, 12, 0, 0),
            original_url=url,
            success=True,
            attempts=1,
            last_error=None,
        )
        metadata_file = snapshot_dir / "metadata.json"
        metadata.save_to_file(metadata_file)

        # Create context with HTML content
        content = f'<a href="{url}">Example Link</a>'
        ctx = PageContext(
            source_path=Path("test.md"),
            relative_path=Path("test.md"),
            output_path=Path("test.html"),
            raw_content="",
            content=content,
        )

        result_ctx = plugin._update_links_with_metadata(ctx, {url})

        soup = BeautifulSoup(result_ctx.content, "html.parser")
        link = soup.find("a")

        assert link["data-snapshot-id"] == plugin._get_url_hash(url)
        assert link["data-snapshot-date"] == "2023-01-01T12:00:00"
        assert link["data-snapshot-url"] == url

    def test_update_links_no_metadata(self, plugin):
        """Test updating links when no metadata exists."""
        url = "https://example.com"
        content = f'<a href="{url}">Example Link</a>'
        ctx = PageContext(
            source_path=Path("test.md"),
            relative_path=Path("test.md"),
            output_path=Path("test.html"),
            raw_content="",
            content=content,
        )

        result_ctx = plugin._update_links_with_metadata(ctx, {url})

        soup = BeautifulSoup(result_ctx.content, "html.parser")
        link = soup.find("a")

        # Should not have snapshot attributes
        assert "data-snapshot-id" not in link.attrs
        assert "data-snapshot-date" not in link.attrs
        assert "data-snapshot-url" not in link.attrs

    @patch.object(SnapshotPlugin, "_snapshot_urls")
    @patch.object(SnapshotPlugin, "_update_links_with_metadata")
    async def test_process_with_urls(
        self, mock_update, mock_snapshot, plugin, base_context
    ):
        """Test processing content with URLs."""
        content = '<p>Check out <a href="https://example.com">this</a> and <a href="https://test.org">that</a>.</p>'
        base_context.content = content

        mock_update.return_value = base_context

        await plugin.process(base_context)

        # Should call snapshot_urls and update_links
        mock_snapshot.assert_called_once()
        mock_update.assert_called_once()

        # Check that URLs were extracted
        called_urls = mock_snapshot.call_args[0][0]
        assert "https://example.com" in called_urls
        assert "https://test.org" in called_urls

    @patch.object(SnapshotPlugin, "_snapshot_urls")
    async def test_process_no_urls(self, mock_snapshot, plugin, base_context):
        """Test processing content with no URLs."""
        base_context.content = "This content has no external links."

        result = await plugin.process(base_context)

        # Should not call snapshot_urls
        mock_snapshot.assert_not_called()
        assert result.content == base_context.content

    async def test_process_preserves_context(self, plugin, base_context):
        """Test that process preserves other context fields."""
        base_context.content = "No URLs here"
        base_context.title = "Test Title"
        base_context.tags = ["test"]

        result = await plugin.process(base_context)

        assert result.title == "Test Title"
        assert result.tags == ["test"]
        assert result.source_path == base_context.source_path

    @pytest.mark.parametrize(
        "content,expected_extracted",
        [
            ('<a href="https://example.com">Link</a>', True),
            ('<a href="http://example.com">Link</a>', True),
            ('<a href="www.example.com">Link</a>', True),
            ('<a href="./local.html">Link</a>', False),
            ('<a href="../relative.html">Link</a>', False),
            ('<a href="/absolute/path.html">Link</a>', False),
            (
                '<img src="https://example.com/img.jpg" alt="Image">',
                False,
            ),  # Images ignored
            ("<p>Text without links</p>", False),  # No links
        ],
    )
    def test_url_extraction_patterns(self, plugin, content, expected_extracted):
        """Test various URL patterns for extraction."""
        urls = plugin._extract_urls_from_content(content)

        if expected_extracted:
            assert len(urls) == 1
        else:
            assert len(urls) == 0
