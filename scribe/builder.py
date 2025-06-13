"""Core builder for processing markdown files and generating static site."""

import asyncio
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from scribe.build_plugins.config import (
    BaseBuildPluginConfig,
    LinkResolutionBuildPluginConfig,
)
from scribe.build_plugins.manager import BuildPluginManager
from scribe.config import ScribeConfig
from scribe.context import PageContext, PageStatus
from scribe.logger import get_logger
from scribe.note_plugins import PluginManager
from scribe.note_plugins.config import (
    BaseNotePluginConfig,
    DatePluginConfig,
    FootnotesPluginConfig,
    FrontmatterPluginConfig,
    MarkdownPluginConfig,
)
from scribe.predicates import PredicateMatcher
from scribe.templates import NotesAccessor

console = Console()
logger = get_logger(__name__)


class SiteBuilder:
    """Main builder class for processing files and generating static site."""

    def __init__(self, config: ScribeConfig) -> None:
        self.config = config
        self.plugin_manager = PluginManager(global_config=config)
        self.build_plugin_manager = BuildPluginManager()
        self.jinja_env: Environment | None = None
        self.predicate_matcher = PredicateMatcher()
        self.predicate_functions: dict[str, Callable[[PageContext], bool]] = {}
        self.processed_notes: list[PageContext] = []
        self.build_errors: dict[str, list[str]] = {}  # filename -> list of errors

        self.default_plugins: list[BaseNotePluginConfig] = [
            FrontmatterPluginConfig(),
            FootnotesPluginConfig(),
            MarkdownPluginConfig(),
            DatePluginConfig(),
        ]

        self.default_build_plugins: list[BaseBuildPluginConfig] = [
            LinkResolutionBuildPluginConfig(),
        ]

        self._setup_plugins()
        self._setup_build_plugins()
        self._setup_templates()

    def _setup_plugins(self) -> None:
        """Setup default plugins and load custom plugins from config."""
        # Combine default plugins with user-configured plugins
        all_plugins = list(self.default_plugins)

        if self.config.note_plugins:
            # Add user-configured plugins, avoiding duplicates
            default_plugin_names = {plugin.name for plugin in self.default_plugins}

            # Only add user plugins that don't override defaults
            for plugin in self.config.note_plugins:
                if plugin.name in default_plugin_names:
                    # Replace default plugin with user configuration
                    all_plugins = [p for p in all_plugins if p.name != plugin.name]
                all_plugins.append(plugin)

        # Load all plugins together so dependency resolution sees everything
        self.plugin_manager.load_plugins_from_config(all_plugins)

    def _setup_build_plugins(self) -> None:
        """Setup default build plugins and load custom build plugins from config."""
        # Combine default build plugins with user-configured build plugins
        all_build_plugins = list(self.default_build_plugins)

        if self.config.build_plugins:
            # Add user-configured build plugins, avoiding duplicates
            default_build_plugin_names = {
                plugin.name for plugin in self.default_build_plugins
            }

            # Only add user plugins that don't override defaults
            for plugin in self.config.build_plugins:
                if plugin.name in default_build_plugin_names:
                    # Replace default plugin with user configuration
                    all_build_plugins = [
                        p for p in all_build_plugins if p.name != plugin.name
                    ]
                all_build_plugins.append(plugin)

        # Load all build plugins together so dependency resolution sees everything
        self.build_plugin_manager.load_plugins_from_config(all_build_plugins)

    def _setup_templates(self) -> None:
        """Setup Jinja2 template environment if templates are configured."""
        if not self.config.templates or not self.config.templates.template_path:
            return

        template_path = self.config.templates.template_path
        if not template_path.exists():
            console.print(
                f"[yellow]Warning: Template directory {template_path} "
                "does not exist[/yellow]"
            )
            return

        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_path)), autoescape=True
        )

        # Setup predicate functions from the predicate matcher
        self.predicate_functions = self.predicate_matcher.predicate_functions

    async def build_site(self, force_rebuild: bool = False) -> None:
        """Build the entire site."""
        if self.config.clean_output and self.config.output_dir.exists():
            shutil.rmtree(self.config.output_dir)

        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        # Clear processed notes cache and error tracking
        self.processed_notes.clear()
        self.build_errors.clear()

        # Execute build plugins before_notes phase
        try:
            await self.build_plugin_manager.execute_before_notes(
                self.config, self.config.output_dir
            )
        except Exception as e:
            self.build_errors["build_plugins_before_notes"] = [
                f"Before notes plugin error: {e}"
            ]

        # Ensure the input path exists
        if not self.config.source_dir.exists():
            raise FileNotFoundError(
                f"Input directory {self.config.source_dir} does not exist"
            )

        # Find all markdown files
        markdown_files = self._find_markdown_files()

        # Process files concurrently (just processing, not writing output yet)
        tasks = [
            self._process_file_content(file_path, force_rebuild)
            for file_path in markdown_files
        ]

        results = await self._process_files_with_progress(tasks)

        # Collect processed notes (filter out None results)
        self.processed_notes = [ctx for ctx in results if ctx is not None]

        # Execute build plugins after_notes phase (can modify contexts)
        try:
            self.processed_notes = await self.build_plugin_manager.execute_after_notes(
                self.config, self.config.output_dir, self.processed_notes
            )
        except Exception as e:
            # Try to extract which file caused the error from the exception message
            file_key = self._extract_file_from_error(str(e))
            if file_key not in self.build_errors:
                self.build_errors[file_key] = []
            self.build_errors[file_key].append(f"Build plugin error: {e}")

        # Generate output based on note templates
        await self._generate_outputs_from_templates(force_rebuild)

        # Build base templates if configured
        await self._build_base_templates()

        # Copy static files if configured
        await self._copy_static_files()

        # Execute build plugins after_all phase
        try:
            await self.build_plugin_manager.execute_after_all(
                self.config, self.config.output_dir
            )
        except Exception as e:
            self.build_errors["build_plugins_after_all"] = [
                f"After all plugin error: {e}"
            ]

        # Copy snapshot outputs after all processing is complete
        self.plugin_manager.copy_snapshot_outputs(self.config.output_dir)

        # Report any validation errors that occurred during the build
        self._report_build_errors()

    async def build_file(self, file_path: Path) -> PageContext | None:
        """Build a single file and return its context."""
        # Process the file content
        ctx = await self._process_file_content(file_path, force_rebuild=True)
        if ctx is None:
            return None

        # Generate output if it matches any template
        await self._generate_output_for_note(ctx, force_rebuild=True)
        return ctx

    def _find_markdown_files(self) -> list[Path]:
        """Find all markdown files in the source directory."""
        if not self.config.source_dir.exists():
            return []

        markdown_files = []
        for pattern in ["*.md", "*.markdown"]:
            markdown_files.extend(self.config.source_dir.rglob(pattern))

        return markdown_files

    async def _process_file_content(
        self, file_path: Path, force_rebuild: bool = False
    ) -> PageContext | None:
        """Process a single markdown file content through plugins."""
        try:
            # Check if file needs rebuilding
            if not force_rebuild and not self._needs_rebuild(file_path):
                return None

            logger.info(
                f"Processing note: {file_path.relative_to(self.config.source_dir)}"
            )

            # Create page context
            ctx = self._create_page_context(file_path)

            # Process through plugins
            try:
                ctx = await self.plugin_manager.process_page(ctx)
            except Exception as e:
                self.build_errors[str(file_path)] = [f"Plugin error: {e}"]
                return None

            # Update output path based on matching note template URL pattern
            self._update_output_path_from_template(ctx)

            # Always return context for notes collection
            return ctx

        except Exception as e:
            console.print(f"[red]Error processing {file_path}:[/red] {e}")
            # Also track this as a build error
            file_key = str(file_path.relative_to(self.config.source_dir))
            self.build_errors[file_key] = [f"Processing error: {e}"]
            return None

    async def _process_files_with_progress(
        self, tasks: list, max_concurrent: int = 10
    ) -> list[PageContext | None]:
        """Process files concurrently with a progress bar, limited by semaphore."""
        if not tasks:
            return []

        # Create semaphore to limit concurrent operations
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _process_with_semaphore(coro):
            """Wrapper to run coroutine with semaphore."""
            async with semaphore:
                return await coro

        # Wrap all tasks with semaphore
        semaphored_tasks = [_process_with_semaphore(task) for task in tasks]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task_id = progress.add_task(
                f"Processing {len(tasks)} files ({max_concurrent} concurrent)...",
                total=len(tasks),
            )

            results = []
            for coro in asyncio.as_completed(semaphored_tasks):
                result = await coro
                results.append(result)
                progress.advance(task_id)

            return results

    def _create_page_context(self, file_path: Path) -> PageContext:
        """Create a page context for a markdown file."""
        # Read file content
        content = file_path.read_text(encoding="utf-8")

        # Calculate relative path from source directory
        relative_path = file_path.relative_to(self.config.source_dir)

        # Calculate output path (replace .md with .html)
        output_relative = relative_path.with_suffix(".html")
        output_path = self.config.output_dir / output_relative

        # Get file modification time
        modified_time = file_path.stat().st_mtime

        return PageContext(
            source_path=file_path,
            relative_path=relative_path,
            output_path=output_path,
            raw_content=content,
            modified_time=modified_time,
        )

    def _needs_rebuild(self, file_path: Path) -> bool:
        """Check if a file needs to be rebuilt."""
        # For now, always rebuild during content processing phase
        # The template-based output generation will handle the actual rebuild logic
        return True

    async def _build_base_templates(self) -> None:
        """Build base templates that are copied 1:1 to HTML."""
        if not self.config.templates or not self.jinja_env:
            return

        for template_path in self.config.templates.base_templates:
            try:
                template = self.jinja_env.get_template(template_path)

                # Create global context for template
                global_context = self._create_global_context()

                # Render template
                rendered_content = template.render(**global_context)

                # Determine output path
                output_path = self.config.output_dir / Path(template_path).with_suffix(
                    ".html"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Write output
                output_path.write_text(rendered_content, encoding="utf-8")

            except Exception as e:
                console.print(
                    f"[red]Error building base template {template_path}:[/red] {e}"
                )

    def _create_global_context(self) -> dict[str, Any]:
        """Create global context for templates."""
        return {
            "site": {
                "title": self.config.site_title,
                "description": self.config.site_description,
                "url": self.config.site_url,
            },
            "config": self.config.model_dump(),
            "build_metadata": {
                "generator": "Scribe",
                "version": "1.0.0",
                "build_time": datetime.now().isoformat(),
            },
            "notes": NotesAccessor(self.processed_notes, self.predicate_matcher),
        }

    async def _copy_static_files(self) -> None:
        """Copy static files to output directory, merging with existing content."""
        if not self.config.static_path or not self.config.static_path.exists():
            return

        static_path = self.config.static_path
        output_path = self.config.output_dir

        # Walk through all files in static directory
        for item in static_path.rglob("*"):
            if item.is_file():
                # Calculate relative path from static_path
                relative_path = item.relative_to(static_path)

                # Determine output location
                output_file = output_path / relative_path

                # Create parent directories if they don't exist
                output_file.parent.mkdir(parents=True, exist_ok=True)

                # Copy file if it doesn't exist or is newer
                if (
                    not output_file.exists()
                    or item.stat().st_mtime > output_file.stat().st_mtime
                ):
                    try:
                        shutil.copy2(item, output_file)
                        console.print(
                            f"[green]Copied static file:[/green] {relative_path}"
                        )
                    except Exception as e:
                        console.print(f"[red]Error copying {item}:[/red] {e}")

    async def _write_output_file(self, ctx: PageContext) -> None:
        """Write the processed content to output file."""
        # Ensure output directory exists
        ctx.output_path.parent.mkdir(parents=True, exist_ok=True)

        # For now, just write the HTML content
        # In a full implementation, this would use templates
        html_content = self._generate_html(ctx)

        ctx.output_path.write_text(html_content, encoding="utf-8")

    def _generate_html(self, ctx: PageContext) -> str:
        """Generate HTML for a page context."""
        # Try to use note templates first
        if self.config.templates and self.jinja_env:
            template_content = self._render_with_note_templates(ctx)
            if template_content:
                return template_content

        # Fall back to simple HTML template
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ctx.title or "Untitled"}</title>
    {
            f'<meta name="description" content="{ctx.description}">'
            if ctx.description
            else ""
        }
</head>
<body>
    <main>
        <article>
            {f"<h1>{ctx.title}</h1>" if ctx.title else ""}
            {f'<p class="meta">By {ctx.author}</p>' if ctx.author else ""}
            {f'<p class="meta">{ctx.date}</p>' if ctx.date else ""}
            <div class="content">
                {ctx.content}
            </div>
            {f'<div class="tags">Tags: {", ".join(ctx.tags)}</div>' if ctx.tags else ""}
        </article>
    </main>
</body>
</html>"""

    def _render_with_note_templates(self, ctx: PageContext) -> str | None:
        """Try to render the page context with note templates."""
        if not self.config.templates or not self.jinja_env:
            return None

        # Find matching template
        for note_template in self.config.templates.note_templates:
            if self._note_matches_template(ctx, note_template):
                try:
                    template = self.jinja_env.get_template(note_template.template_path)

                    # Create template context
                    template_context = self._create_note_template_context(ctx)

                    # Render template
                    return template.render(**template_context)

                except Exception as e:
                    console.print(
                        f"[red]Error rendering template "
                        f"{note_template.template_path}:[/red] {e}"
                    )
                    continue

        return None

    def _note_matches_template(self, ctx: PageContext, note_template) -> bool:
        """Check if a note context matches a template's predicates."""
        # If no predicates, match all
        if not note_template.predicates:
            return True

        # Use the predicate matcher to check predicates
        return self.predicate_matcher.matches_predicates(
            ctx, tuple(note_template.predicates)
        )

    async def _generate_outputs_from_templates(self, force_rebuild: bool) -> None:
        """Generate outputs for notes based on note templates."""
        if not self.config.templates or not self.config.templates.note_templates:
            logger.debug("No note templates configured, skipping output generation")
            return

        # Track which notes have been processed to avoid duplicates
        processed_notes = set()

        # Iterate through each note template
        for note_template in self.config.templates.note_templates:
            logger.debug(f"Processing template: {note_template.template_path}")

            # Find notes that match this template
            matching_notes = []
            for ctx in self.processed_notes:
                if ctx.source_path in processed_notes:
                    continue  # Skip if already processed by another template

                if self._note_matches_template(ctx, note_template):
                    # Check status requirements - only generate for DRAFT or PUBLISH
                    if force_rebuild or ctx.status in (
                        PageStatus.DRAFT,
                        PageStatus.PUBLISH,
                    ):
                        matching_notes.append(ctx)
                        processed_notes.add(ctx.source_path)

            # Generate output for matching notes
            logger.info(
                f"Template '{note_template.template_path}' matches "
                f"{len(matching_notes)} notes"
            )

            for ctx in matching_notes:
                await self._generate_output_for_note(ctx, force_rebuild)

    async def _generate_output_for_note(
        self, ctx: PageContext, force_rebuild: bool
    ) -> None:
        """Generate output for a single note."""
        # Log the final URL/path for this note
        relative_output = ctx.output_path.relative_to(self.config.output_dir)
        logger.info(f"Note '{ctx.title or ctx.source_path.stem}' → /{relative_output}")

        # Write output file
        await self._write_output_file(ctx)
        logger.info(f"Written output file: {ctx.output_path}")

    def _update_output_path_from_template(self, ctx: PageContext) -> None:
        """Update the output path based on matching note template URL pattern."""
        if not self.config.templates or not self.config.templates.note_templates:
            return

        # Find the first matching template
        for note_template in self.config.templates.note_templates:
            if self._note_matches_template(ctx, note_template):
                # Generate output path from URL pattern
                url_pattern = note_template.url_pattern

                logger.debug(
                    f"Note matches template '{note_template.template_path}' "
                    f"with URL pattern '{url_pattern}'"
                )

                # Replace {slug} with actual slug
                if "{slug}" in url_pattern:
                    url_path = url_pattern.replace("{slug}", ctx.slug or "untitled")
                else:
                    url_path = url_pattern

                # Remove leading slash and convert to path
                url_path = url_path.lstrip("/")

                # If URL ends with '/', treat it as a directory and add index.html
                if url_path.endswith("/"):
                    output_path = self.config.output_dir / url_path / "index.html"
                else:
                    # Otherwise, add .html extension if not present
                    if not url_path.endswith(".html"):
                        url_path += ".html"
                    output_path = self.config.output_dir / url_path

                # Update the context's output path
                ctx.output_path = output_path
                logger.debug(f"Updated output path to: {output_path}")
                return

    def _create_note_template_context(self, ctx: PageContext) -> dict[str, Any]:
        """Create template context for note templates."""
        # Start with global context
        template_context = self._create_global_context()

        # Add note-specific context
        template_context["note"] = ctx.model_dump(mode="json")

        # Add plugin functions to template context
        self._add_plugin_functions_to_context(template_context, ctx)

        return template_context

    def _add_plugin_functions_to_context(
        self, template_context: dict[str, Any], ctx: PageContext
    ) -> None:
        """Add plugin functions to template context."""
        # Image helper has been removed

        # Add other plugin functions as needed
        # This can be extended for other plugins that provide template functions

    def _report_build_errors(self) -> None:
        """Report any validation or processing errors that occurred during the build."""
        if not self.build_errors:
            return

        console.print("\n[yellow]Build completed with the following errors:[/yellow]")
        console.print()

        for file_path, errors in self.build_errors.items():
            console.print(f"[red]File: {file_path}[/red]")
            for error in errors:
                console.print(f"  • {error}")
            console.print()

        error_count = sum(len(errors) for errors in self.build_errors.values())
        file_count = len(self.build_errors)
        console.print(
            f"[yellow]Total: {error_count} error(s) in {file_count} file(s)[/yellow]"
        )
        console.print()

    def cleanup(self) -> None:
        """Cleanup resources."""
        self.plugin_manager.teardown()
        self.build_plugin_manager.teardown()

    def _extract_file_from_error(self, error_message: str) -> str:
        """Extract the source file path from an error message when possible."""
        # Look for patterns like "referenced in '/path/to/file.md'"
        import re

        # Try to extract file path from common error patterns
        patterns = [
            r"referenced in '([^']+)'",
            r"in file '([^']+)'",
            r"from '([^']+)'",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_message)
            if match:
                file_path = match.group(1)
                # Convert to relative path if it's within our source directory
                try:
                    file_path_obj = Path(file_path)
                    if file_path_obj.is_relative_to(self.config.source_dir):
                        return str(file_path_obj.relative_to(self.config.source_dir))
                    else:
                        return str(file_path_obj.name)  # Just use filename
                except (ValueError, OSError):
                    return file_path

        # If no file found in error message, use a generic key
        return "unknown_file"
