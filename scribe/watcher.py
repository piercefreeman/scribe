"""File watching and automatic rebuilding for development."""

import asyncio
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from rich.console import Console
from watchfiles import awatch

from scribe.builder import SiteBuilder
from scribe.config import ScribeConfig
from scribe.dev_builder import DevSiteBuilder

console = Console()

# Global list of reload queues for SSE clients
reload_clients: list[asyncio.Queue] = []


class FileWatcher:
    """Watches for file changes and triggers rebuilds."""

    def __init__(self, config: ScribeConfig, builder: SiteBuilder) -> None:
        self.config = config
        self.builder = builder
        self.is_watching = False
        self._watch_task: asyncio.Task | None = None
        self._debounce_delay = 0.5  # Seconds to wait before rebuilding
        self._pending_changes: set[Path] = set()
        self._rebuild_timer: asyncio.Task | None = None

    async def start_watching(self, on_change: Callable | None = None) -> None:
        """Start watching for file changes."""
        if self.is_watching:
            return

        self.is_watching = True

        # Watch source directory for markdown files
        watch_paths = [self.config.source_dir]

        # Watch templates directory if configured
        if self.config.templates and self.config.templates.template_path:
            if self.config.templates.template_path.exists():
                watch_paths.append(self.config.templates.template_path)

        # Also watch config file if it exists
        config_file = self.config.config_dir / "config.yml"
        if config_file.exists():
            watch_paths.append(config_file)

        console.print(
            f"[dim]Watching for changes in:[/dim] "
            f"{', '.join(str(p) for p in watch_paths)}"
        )

        self._watch_task = asyncio.create_task(
            self._watch_files(watch_paths, on_change)
        )

    async def stop_watching(self) -> None:
        """Stop watching for file changes."""
        if not self.is_watching:
            return

        self.is_watching = False

        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        if self._rebuild_timer:
            self._rebuild_timer.cancel()
            try:
                await self._rebuild_timer
            except asyncio.CancelledError:
                pass

    async def _watch_files(
        self, watch_paths: list[Path], on_change: Callable | None = None
    ) -> None:
        """Watch files and handle changes."""
        try:
            async for changes in awatch(
                *watch_paths, watch_filter=self._should_watch_file
            ):
                if not self.is_watching:
                    break

                # Collect changed files
                changed_files = set()
                template_changed = False

                for _change_type, file_path in changes:
                    path = Path(file_path)

                    # Handle config file changes
                    if path.name == "config.yml":
                        console.print(
                            "[yellow]Configuration changed, rebuilding entire "
                            "site...[/yellow]"
                        )
                        await self._rebuild_site()
                        if on_change:
                            await on_change("config", path)
                        continue

                    # Handle template file changes - rebuild entire site
                    if path.suffix.lower() in {
                        ".j2",
                        ".jinja",
                        ".jinja2",
                        ".html",
                        ".htm",
                    }:
                        template_changed = True
                        continue

                    # Only process markdown files
                    if path.suffix.lower() in {".md", ".markdown"}:
                        changed_files.add(path)

                # If template changed, rebuild entire site
                if template_changed:
                    console.print(
                        "[yellow]Template changed, rebuilding entire site...[/yellow]"
                    )
                    await self._rebuild_site()
                    if on_change:
                        await on_change("template", None)
                    continue

                if changed_files:
                    self._pending_changes.update(changed_files)
                    await self._schedule_rebuild(on_change)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            console.print(f"[red]Error watching files:[/red] {e}")

    def _should_watch_file(self, change_type: str, file_path: str) -> bool:
        """Filter which files to watch."""
        path = Path(file_path)

        # Watch config files
        if path.name == "config.yml":
            return True

        # Watch markdown files
        if path.suffix.lower() in {".md", ".markdown"}:
            return True

        # Watch template files (Jinja2 templates)
        if path.suffix.lower() in {".j2", ".jinja", ".jinja2", ".html", ".htm"}:
            return True

        # Ignore hidden files and directories
        if any(part.startswith(".") for part in path.parts):
            return False

        return False

    async def _schedule_rebuild(self, on_change: Callable | None = None) -> None:
        """Schedule a rebuild with debouncing."""
        # Cancel existing timer
        if self._rebuild_timer:
            self._rebuild_timer.cancel()

        # Schedule new rebuild
        self._rebuild_timer = asyncio.create_task(self._debounced_rebuild(on_change))

    async def _debounced_rebuild(self, on_change: Callable | None = None) -> None:
        """Wait for debounce delay then rebuild changed files."""
        try:
            await asyncio.sleep(self._debounce_delay)

            if self._pending_changes:
                changes = self._pending_changes.copy()
                self._pending_changes.clear()

                # Start timing the rebuild
                start_time = time.perf_counter()

                console.print(
                    f"[blue]Rebuilding {len(changes)} changed file(s)...[/blue]"
                )

                # Rebuild each changed file
                rebuilt_count = 0
                removed_count = 0
                error_count = 0

                for file_path in changes:
                    try:
                        if file_path.exists():
                            await self.builder.build_file(file_path)
                            console.print(
                                f"[green]✓ Rebuilt:[/green] "
                                f"{file_path.relative_to(self.config.source_dir)}"
                            )
                            rebuilt_count += 1
                        else:
                            # File was deleted, remove output
                            await self._handle_deleted_file(file_path)
                            console.print(
                                f"[red]✗ Removed:[/red] "
                                f"{file_path.relative_to(self.config.source_dir)}"
                            )
                            removed_count += 1
                    except Exception as e:
                        console.print(f"[red]Error rebuilding {file_path}:[/red] {e}")
                        error_count += 1

                # Calculate and display timing
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000

                # Build summary message
                summary_parts = []
                if rebuilt_count > 0:
                    summary_parts.append(f"[green]{rebuilt_count} rebuilt[/green]")
                if removed_count > 0:
                    summary_parts.append(f"[red]{removed_count} removed[/red]")
                if error_count > 0:
                    summary_parts.append(f"[red]{error_count} errors[/red]")

                summary = ", ".join(summary_parts) if summary_parts else "no changes"
                console.print(f"[dim]✓ Done ({summary}) in {duration_ms:.1f}ms[/dim]")

                # Signal reload for all SSE clients
                for client_queue in reload_clients[
                    :
                ]:  # Copy list to avoid modification during iteration
                    try:
                        client_queue.put_nowait("reload")
                    except asyncio.QueueFull:
                        # Remove full queues (disconnected clients)
                        reload_clients.remove(client_queue)

                if on_change:
                    await on_change("files", changes)

        except asyncio.CancelledError:
            pass

    async def _handle_deleted_file(self, file_path: Path) -> None:
        """Handle deletion of a source file."""
        try:
            # Calculate corresponding output file
            relative_path = file_path.relative_to(self.config.source_dir)
            output_path = self.config.output_dir / relative_path.with_suffix(".html")

            if output_path.exists():
                output_path.unlink()
        except Exception as e:
            console.print(f"[red]Error removing output file for {file_path}:[/red] {e}")

    async def _rebuild_site(self) -> None:
        """Rebuild the entire site."""
        try:
            start_time = time.perf_counter()
            await self.builder.build_site(force_rebuild=True)
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            console.print(
                f"[green]✓ Site rebuilt successfully[/green] "
                f"[dim]in {duration_ms:.1f}ms[/dim]"
            )

            # Signal reload for all SSE clients
            for client_queue in reload_clients[
                :
            ]:  # Copy list to avoid modification during iteration
                try:
                    client_queue.put_nowait("reload")
                except asyncio.QueueFull:
                    # Remove full queues (disconnected clients)
                    reload_clients.remove(client_queue)
        except Exception as e:
            console.print(f"[red]Error rebuilding site:[/red] {e}")


class DevWebServer:
    """Web server component for development with SSE support."""

    def __init__(self, config: ScribeConfig, temp_output_dir: Path) -> None:
        self.config = config
        self.temp_output_dir = temp_output_dir
        self.app = self._create_app()
        self.server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with SSE and static file serving."""
        app = FastAPI(title="Scribe Dev Server")

        # Add SSE endpoint for live reloading
        @app.get("/_dev/reload")
        async def reload_endpoint():
            # Create a queue for this client
            client_queue = asyncio.Queue(maxsize=10)
            reload_clients.append(client_queue)

            # TODO: Fix control-C issue
            return

            async def event_stream():
                try:
                    # Send initial connection message
                    yield "data: connected\n\n"

                    while True:
                        # Wait for reload signal from queue
                        message = await client_queue.get()
                        yield f"data: {message}\n\n"
                        client_queue.task_done()
                except asyncio.CancelledError:
                    pass
                finally:
                    # Remove client queue when connection closes
                    if client_queue in reload_clients:
                        reload_clients.remove(client_queue)

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Cache-Control",
                },
            )

        # Add custom route handler for extensionless URLs
        @app.get("/{path:path}")
        async def serve_files(request: Request, path: str = ""):
            return await self._serve_file_with_fallback(path)

        # Mount static files as fallback for direct file access
        app.mount("/static", StaticFiles(directory=self.temp_output_dir), name="static")

        return app

    async def _serve_file_with_fallback(self, path: str) -> Response:
        """Serve files with nginx-like extensionless URL support."""
        # Normalize path - remove leading/trailing slashes and handle empty path
        path = path.strip("/")
        if not path:
            path = "index"

        # Try different file resolution strategies
        candidates = []

        # 1. Direct file match (if path has extension)
        if "." in path:
            candidates.append(path)
        else:
            # 2. Try with .html extension first
            candidates.extend(
                [
                    f"{path}.html",
                    f"{path}/index.html",
                    path,  # Try as directory
                ]
            )

        # Try each candidate file
        for candidate in candidates:
            file_path = self.temp_output_dir / candidate
            if file_path.is_file():
                # Determine content type
                content_type = self._get_content_type(file_path)
                return FileResponse(
                    path=file_path,
                    media_type=content_type,
                    headers={"Cache-Control": "no-cache"},  # Prevent caching in dev
                )

        # If no file found, return 404
        return Response(
            content="<h1>404 Not Found</h1><p>The requested file was not found.</p>",
            status_code=404,
            media_type="text/html",
        )

    def _get_content_type(self, file_path: Path) -> str:
        """Get content type based on file extension."""
        suffix = file_path.suffix.lower()
        content_types = {
            ".html": "text/html",
            ".htm": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".eot": "application/vnd.ms-fontobject",
        }
        return content_types.get(suffix, "application/octet-stream")

    async def start(self) -> None:
        """Start the web server."""
        uvicorn_config = uvicorn.Config(
            app=self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="warning",  # Reduce log noise in dev mode
        )
        self.server = uvicorn.Server(uvicorn_config)
        self._server_task = asyncio.create_task(self.server.serve())

    async def stop(self) -> None:
        """Stop the web server."""
        if self.server:
            self.server.should_exit = True

        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        # Close all SSE connections by sending disconnect signal
        for client_queue in reload_clients[:]:
            try:
                client_queue.put_nowait("disconnect")
            except asyncio.QueueFull:
                pass

        # Clear all SSE clients
        reload_clients.clear()

    async def wait_for_completion(self) -> None:
        """Wait for the server task to complete."""
        if self._server_task:
            await self._server_task


class DevServer:
    """Development server that combines file watching with serving."""

    def __init__(self, config: ScribeConfig) -> None:
        self.config = config
        self.builder = DevSiteBuilder(config)  # Use development builder
        self.watcher = FileWatcher(config, self.builder)
        self.temp_dir: tempfile.TemporaryDirectory | None = None
        self.web_server: DevWebServer | None = None

    async def start(self) -> None:
        """Start the development server with file watching."""
        console.print("[blue]Starting development server...[/blue]")

        # Create temporary directory for dev server output
        self.temp_dir = tempfile.TemporaryDirectory(prefix="scribe-dev-")
        temp_output = Path(self.temp_dir.name)
        self.config.output_dir = temp_output

        console.print(f"[dim]Using temporary output directory:[/dim] {temp_output}")

        # Update builder with new output directory
        self.builder = DevSiteBuilder(self.config)
        self.watcher = FileWatcher(self.config, self.builder)

        # Initial build
        console.print("[dim]Building site...[/dim]")
        start_time = time.perf_counter()
        await self.builder.build_site()
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        console.print(
            f"[green]✓ Initial build complete[/green] [dim]in {duration_ms:.1f}ms[/dim]"
        )

        # Start web server
        self.web_server = DevWebServer(self.config, temp_output)
        await self.web_server.start()

        # Start file watcher
        await self.watcher.start_watching(self._on_file_change)

        console.print(
            f"[green]🚀 Development server running at[/green] [cyan]http://{self.config.host}:{self.config.port}[/cyan]"
        )
        console.print("[dim]Press Ctrl+C to stop[/dim]")

    async def stop(self) -> None:
        """Stop the development server."""
        console.print("[yellow]Stopping development server...[/yellow]")

        await self.watcher.stop_watching()

        if self.web_server:
            await self.web_server.stop()

        self.builder.cleanup()

        if self.temp_dir:
            self.temp_dir.cleanup()

    async def _on_file_change(self, change_type: str, files) -> None:
        """Handle file change events."""
        if change_type == "config":
            console.print("[yellow]Configuration reloaded[/yellow]")
        elif change_type == "files":
            console.print(f"[green]✓ Rebuilt {len(files)} file(s)[/green]")

    async def serve_forever(self) -> None:
        """Run the development server forever."""
        try:
            await self.start()

            # Wait for web server to complete
            if self.web_server:
                await self.web_server.wait_for_completion()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self.stop()
