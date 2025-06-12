"""Tests for development server functionality."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from scribe.config import ScribeConfig
from scribe.watcher import DevServer, DevWebServer, reload_clients


@pytest.fixture
def temp_config():
    """Create a temporary config for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        config = ScribeConfig()
        config.source_dir = temp_path / "content"
        config.output_dir = temp_path / "output"
        config.host = "127.0.0.1"
        config.port = 8000

        # Create directories
        config.source_dir.mkdir(exist_ok=True)
        config.output_dir.mkdir(exist_ok=True)

        yield config


@pytest.fixture
def dev_web_server(temp_config):
    """Create a DevWebServer instance for testing."""
    temp_output = temp_config.output_dir
    return DevWebServer(temp_config, temp_output)


@pytest.fixture
def dev_server(temp_config):
    """Create a DevServer instance for testing."""
    return DevServer(temp_config)


class TestDevWebServer:
    """Test cases for DevWebServer class."""

    def test_init(self, dev_web_server, temp_config):
        """Test DevWebServer initialization."""
        assert dev_web_server.config == temp_config
        assert dev_web_server.temp_output_dir == temp_config.output_dir
        assert dev_web_server.app is not None
        assert dev_web_server.server is None
        assert dev_web_server._server_task is None

    def test_create_app(self, dev_web_server):
        """Test FastAPI app creation."""
        app = dev_web_server._create_app()
        assert app.title == "Scribe Dev Server"

        # Check that routes are properly configured
        routes = [route.path for route in app.routes]
        assert "/_dev/reload" in routes
        assert "/{path:path}" in routes  # Custom file serving route
        assert "/static" in routes  # Static files mount

    @pytest.mark.asyncio
    async def test_start_stop(self, dev_web_server):
        """Test starting and stopping the web server."""
        with patch("uvicorn.Server") as mock_server_class:
            mock_server = Mock()
            mock_server_class.return_value = mock_server

            # Mock the serve method
            serve_task = asyncio.create_task(asyncio.sleep(0.1))
            mock_server.serve = AsyncMock(return_value=serve_task)

            # Start server
            await dev_web_server.start()

            assert dev_web_server.server == mock_server
            assert dev_web_server._server_task is not None

            # Stop server
            await dev_web_server.stop()

            assert mock_server.should_exit is True

    @pytest.mark.asyncio
    async def test_sse_client_management(self, dev_web_server):
        """Test SSE client connection and disconnection."""
        # Clear any existing clients
        reload_clients.clear()

        # Simulate client connection
        client_queue = asyncio.Queue(maxsize=10)
        reload_clients.append(client_queue)

        assert len(reload_clients) == 1

        # Test stop method cleans up clients
        await dev_web_server.stop()

        # Should send disconnect message and clear clients
        assert len(reload_clients) == 0


class TestDevServer:
    """Test cases for DevServer class."""

    def test_init(self, dev_server, temp_config):
        """Test DevServer initialization."""
        assert dev_server.config == temp_config
        assert dev_server.builder is not None
        assert dev_server.watcher is not None
        assert dev_server.temp_dir is None
        assert dev_server.web_server is None

    @pytest.mark.asyncio
    async def test_start_creates_temp_directory(self, dev_server):
        """Test that start() creates a temporary directory."""
        with patch.object(dev_server.builder, "build_site", new_callable=AsyncMock):
            with patch.object(
                dev_server.watcher, "start_watching", new_callable=AsyncMock
            ):
                with patch("scribe.watcher.DevWebServer") as mock_web_server_class:
                    mock_web_server = AsyncMock()
                    mock_web_server_class.return_value = mock_web_server

                    await dev_server.start()

                    # Should create temp directory and update config
                    assert dev_server.temp_dir is not None
                    assert dev_server.config.output_dir.exists()
                    assert "scribe-dev-" in str(dev_server.config.output_dir)

    @pytest.mark.asyncio
    async def test_start_builds_site(self, dev_server):
        """Test that start() performs initial site build."""
        with patch("scribe.watcher.DevSiteBuilder") as mock_builder_class:
            mock_builder = AsyncMock()
            mock_builder_class.return_value = mock_builder

            with patch("scribe.watcher.FileWatcher") as mock_watcher_class:
                mock_watcher = AsyncMock()
                mock_watcher_class.return_value = mock_watcher

                with patch("scribe.watcher.DevWebServer") as mock_web_server_class:
                    mock_web_server = AsyncMock()
                    mock_web_server_class.return_value = mock_web_server

                    await dev_server.start()

                    mock_builder.build_site.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_creates_web_server(self, dev_server):
        """Test that start() creates and starts web server."""
        with patch.object(dev_server.builder, "build_site", new_callable=AsyncMock):
            with patch.object(
                dev_server.watcher, "start_watching", new_callable=AsyncMock
            ):
                with patch("scribe.watcher.DevWebServer") as mock_web_server_class:
                    mock_web_server = AsyncMock()
                    mock_web_server_class.return_value = mock_web_server

                    await dev_server.start()

                    # Should create web server
                    mock_web_server_class.assert_called_once()
                    mock_web_server.start.assert_called_once()
                    assert dev_server.web_server == mock_web_server

    @pytest.mark.asyncio
    async def test_start_starts_file_watcher(self, dev_server):
        """Test that start() starts file watching."""
        with patch("scribe.watcher.DevSiteBuilder") as mock_builder_class:
            mock_builder = AsyncMock()
            mock_builder_class.return_value = mock_builder

            with patch("scribe.watcher.FileWatcher") as mock_watcher_class:
                mock_watcher = AsyncMock()
                mock_watcher_class.return_value = mock_watcher

                with patch("scribe.watcher.DevWebServer") as mock_web_server_class:
                    mock_web_server = AsyncMock()
                    mock_web_server_class.return_value = mock_web_server

                    await dev_server.start()

                    mock_watcher.start_watching.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cleanup(self, dev_server):
        """Test that stop() properly cleans up resources."""
        # Setup mocks
        mock_watcher = AsyncMock()
        mock_web_server = AsyncMock()
        mock_builder = Mock()
        mock_temp_dir = Mock()

        dev_server.watcher = mock_watcher
        dev_server.web_server = mock_web_server
        dev_server.builder = mock_builder
        dev_server.temp_dir = mock_temp_dir

        await dev_server.stop()

        # Verify cleanup calls
        mock_watcher.stop_watching.assert_called_once()
        mock_web_server.stop.assert_called_once()
        mock_builder.cleanup.assert_called_once()
        mock_temp_dir.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_file_change_config(self, dev_server):
        """Test file change handler for config changes."""
        with patch("scribe.watcher.console") as mock_console:
            await dev_server._on_file_change("config", None)
            mock_console.print.assert_called_with(
                "[yellow]Configuration reloaded[/yellow]"
            )

    @pytest.mark.asyncio
    async def test_on_file_change_files(self, dev_server):
        """Test file change handler for file changes."""
        with patch("scribe.watcher.console") as mock_console:
            files = [Path("test1.md"), Path("test2.md")]
            await dev_server._on_file_change("files", files)
            mock_console.print.assert_called_with("[green]✓ Rebuilt 2 file(s)[/green]")


class TestDevServerCancellation:
    """Test cases for cancelling dev server after clients connect."""

    @pytest.mark.asyncio
    async def test_serve_forever_cancellation_with_clients(self, temp_config):
        """Test that serve_forever can be cancelled after clients connect."""
        dev_server = DevServer(temp_config)

        # Clear any existing clients
        reload_clients.clear()

        with patch.object(dev_server, "start", new_callable=AsyncMock) as mock_start:
            with patch.object(dev_server, "stop", new_callable=AsyncMock) as mock_stop:
                # Mock the web server wait_for_completion to allow cancellation
                mock_web_server = AsyncMock()
                mock_web_server.wait_for_completion = AsyncMock(
                    side_effect=asyncio.CancelledError()
                )
                dev_server.web_server = mock_web_server

                async def simulate_client_connection():
                    """Simulate a client connecting and then cancel the server."""
                    # Wait a bit to simulate server startup
                    await asyncio.sleep(0.01)

                    # Simulate client connection
                    client_queue = asyncio.Queue(maxsize=10)
                    reload_clients.append(client_queue)

                    # Wait a bit more to ensure client is connected
                    await asyncio.sleep(0.01)

                    # Cancel the serve_forever task
                    serve_task.cancel()

                # Create serve_forever task
                serve_task = asyncio.create_task(dev_server.serve_forever())

                # Create client connection simulation task
                client_task = asyncio.create_task(simulate_client_connection())

                # Wait for both tasks - serve_forever should handle cancellation
                # gracefully
                try:
                    await serve_task
                except asyncio.CancelledError:
                    pass  # Expected behavior

                await client_task

                # Verify that start and stop were called
                mock_start.assert_called_once()
                mock_stop.assert_called_once()

                # Verify client was connected during the test
                assert len(reload_clients) == 1

    @pytest.mark.asyncio
    async def test_web_server_handles_client_cleanup_on_cancellation(self, temp_config):
        """Test that web server properly cleans up clients when cancelled."""
        temp_output = temp_config.output_dir
        web_server = DevWebServer(temp_config, temp_output)

        # Clear any existing clients
        reload_clients.clear()

        # Simulate multiple client connections
        client_queue1 = asyncio.Queue(maxsize=10)
        client_queue2 = asyncio.Queue(maxsize=10)
        reload_clients.extend([client_queue1, client_queue2])

        assert len(reload_clients) == 2

        # Stop web server (should clean up clients)
        await web_server.stop()

        # Verify clients were cleaned up
        assert len(reload_clients) == 0

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_active_connections(self, temp_config):
        """Test graceful shutdown when clients are actively connected."""
        dev_server = DevServer(temp_config)

        # Clear any existing clients
        reload_clients.clear()

        with patch("scribe.watcher.DevSiteBuilder") as mock_builder_class:
            mock_builder = AsyncMock()
            mock_builder_class.return_value = mock_builder

            with patch("scribe.watcher.FileWatcher") as mock_watcher_class:
                mock_watcher = AsyncMock()
                mock_watcher_class.return_value = mock_watcher

                with patch("scribe.watcher.DevWebServer") as mock_web_server_class:
                    mock_web_server = AsyncMock()
                    mock_web_server_class.return_value = mock_web_server

                    # Start the server
                    await dev_server.start()

                    # Simulate client connections
                    client_queue1 = asyncio.Queue(maxsize=10)
                    client_queue2 = asyncio.Queue(maxsize=10)
                    reload_clients.extend([client_queue1, client_queue2])

                    assert len(reload_clients) == 2

                    # Stop the server
                    await dev_server.stop()

                    # Verify proper cleanup sequence
                    mock_watcher.stop_watching.assert_called_once()
                    mock_web_server.stop.assert_called_once()
