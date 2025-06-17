"""Click CLI interface for Scribe."""

import asyncio
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scribe.builder import SiteBuilder
from scribe.config import ScribeConfig
from scribe.watcher import DevServer

console = Console()


def _log_config(config: ScribeConfig) -> None:
    """Log the current configuration during build."""
    console.print("\n[bold blue]Current Configuration:[/bold blue]")

    # Create a table for configuration display
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Setting", style="dim", width=25)
    table.add_column("Value", style="white")

    # Core settings
    table.add_row("Config file:", str(config.config_file_path))
    table.add_row("Environment:", config.environment)
    table.add_row("Source directory:", str(config.source_dir))
    table.add_row("Output directory:", str(config.output_dir))
    table.add_row("Clean output:", "✓" if config.clean_output else "✗")

    # Site metadata
    table.add_row("Site title:", config.site_title)
    table.add_row("Site description:", config.site_description or "[dim]Not set[/dim]")
    table.add_row("Site URL:", config.site_url or "[dim]Not set[/dim]")

    # Development server
    table.add_row("Dev server host:", config.host)
    table.add_row("Dev server port:", str(config.port))

    # Template settings
    if config.templates:
        table.add_row("Template path:", str(config.templates.template_path))
        table.add_row("Base templates:", str(len(config.templates.base_templates)))
        table.add_row("Note templates:", str(len(config.templates.note_templates)))
    else:
        table.add_row("Templates:", "[dim]Not configured[/dim]")

    # Static path
    if config.static_path:
        table.add_row("Static path:", str(config.static_path))
    else:
        table.add_row("Static path:", "[dim]Not configured[/dim]")

    console.print(table)

    # Note plugins
    if config.note_plugins:
        console.print("\n[bold]Note Plugins:[/bold]")
        for plugin in config.note_plugins:
            status = (
                "[green]enabled[/green]" if plugin.enabled else "[red]disabled[/red]"
            )
            console.print(f"  • [cyan]{plugin.name}[/cyan] ({status})")
    else:
        console.print("\n[bold]Note Plugins:[/bold] [dim]Using defaults[/dim]")

    # Build plugins
    if config.build_plugins:
        console.print("\n[bold]Build Plugins:[/bold]")
        for plugin in config.build_plugins:
            status = (
                "[green]enabled[/green]" if plugin.enabled else "[red]disabled[/red]"
            )
            console.print(f"  • [cyan]{plugin.name}[/cyan] ({status})")
    else:
        console.print("\n[bold]Build Plugins:[/bold] [dim]Using defaults[/dim]")

    console.print()  # Add spacing after config


@click.group()
@click.version_option()
def main() -> None:
    """Scribe - A modular static site generator with plugin architecture."""
    pass


@main.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to configuration file (defaults to ~/.scribe/config.yml)",
)
@click.option(
    "--clean/--no-clean", default=True, help="Clean output directory before building"
)
def build(config: Path | None, clean: bool) -> None:
    """Build the static site."""
    site_config = ScribeConfig(config_file=config)

    # Check if config file exists
    if not site_config.config_file_exists():
        console.print(
            f"[red]Error:[/red] No configuration file found at "
            f"{site_config.config_file_path}"
        )
        console.print("Run [cyan]scribe init[/cyan] to create a new project first.")
        raise click.Abort()

    # Override config with CLI options
    site_config.clean_output = clean

    # Log the current configuration
    _log_config(site_config)

    async def _build() -> None:
        builder = SiteBuilder(site_config)
        try:
            console.print(
                f"[green]Building site[/green] from "
                f"[cyan]{site_config.source_dir}[/cyan] to "
                f"[cyan]{site_config.output_dir}[/cyan]"
            )
            start_time = time.perf_counter()
            await builder.build_site()
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            console.print(
                f"[green]✓ Build complete![/green] [dim]in {duration_ms:.1f}ms[/dim]"
            )
        finally:
            builder.cleanup()

    asyncio.run(_build())


@main.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to configuration file (defaults to ~/.scribe/config.yml)",
)
@click.option(
    "--host", "-h", default="127.0.0.1", help="Host to bind the development server"
)
@click.option(
    "--port", "-p", default=8000, type=int, help="Port to bind the development server"
)
def dev(config: Path | None, host: str, port: int) -> None:
    """Start development server with file watching and auto-rebuild."""
    site_config = ScribeConfig(config_file=config)

    # Check if config file exists
    if not site_config.config_file_exists():
        console.print(
            f"[red]Error:[/red] No configuration file found at "
            f"{site_config.config_file_path}"
        )
        console.print("Run [cyan]scribe init[/cyan] to create a new project first.")
        raise click.Abort()

    # Override config with CLI options
    site_config.host = host
    site_config.port = port

    async def _dev() -> None:
        dev_server = DevServer(site_config)
        await dev_server.serve_forever()

    try:
        asyncio.run(_dev())
    except KeyboardInterrupt:
        console.print("\n[yellow]Development server stopped.[/yellow]")


@main.command()
@click.argument("project_path", type=click.Path(path_type=Path), required=True)
@click.option(
    "--force", is_flag=True, help="Force initialization even if config already exists"
)
def init(project_path: Path, force: bool) -> None:
    """Initialize a new Scribe project at the specified path."""
    from scribe.config_mocker import ConfigMocker

    # Resolve the project path
    project_path = project_path.resolve()

    # Create project directory if it doesn't exist
    project_path.mkdir(parents=True, exist_ok=True)

    # Define config file path
    config_file = project_path / "scribe.yml"

    if config_file.exists() and not force:
        console.print(f"[yellow]Configuration already exists at[/yellow] {config_file}")
        console.print("Use [cyan]--force[/cyan] to overwrite")
        return

    # Generate dynamic configuration using ConfigMocker
    mocker = ConfigMocker()
    yaml_content = mocker.generate_yaml_config(ScribeConfig)

    # Write the generated config to file
    config_file.write_text(yaml_content, encoding="utf-8")

    # Create default directories relative to project path
    content_dir = project_path / "content"
    output_dir = project_path / "dist"
    content_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create example content
    example_md = content_dir / "index.md"
    if not example_md.exists():
        example_content = """---
title: Welcome to Scribe
description: A modular static site generator
date: 2024-01-01
tags: [welcome, getting-started]
status: publish
---

# Welcome to Scribe

This is your first page! Edit this file to get started.

## Features

- **Fast**: Built with modern Python and asyncio
- **Modular**: Plugin architecture for extensibility
- **Developer-friendly**: Hot reloading and live preview

## Getting Started

1. Edit this file (`content/index.md`)
2. Run `scribe dev -c scribe.yml` to start the development server
3. Open your browser to see changes in real-time

Happy writing! ✨
"""
        example_md.write_text(example_content)

    # Create additional example content
    about_md = content_dir / "about.md"
    if not about_md.exists():
        about_content = """---
title: About
description: Learn more about this site
date: 2024-01-01
tags: [about]
status: publish
---

# About This Site

This is an example about page. You can customize this content to tell visitors
about yourself or your project.

## What is Scribe?

Scribe is a modular static site generator built with Python. It features:

- Plugin architecture for extensibility
- Fast builds with asyncio
- Hot reloading for development
- Flexible template system

## Get Started

Check out the [main page](/) to learn more about getting started with Scribe.
"""
        about_md.write_text(about_content)

    panel = Panel.fit(
        f"[green]✓ Initialized Scribe project![/green]\n\n"
        f"[dim]Project:[/dim] {project_path}\n"
        f"[dim]Config:[/dim] {config_file}\n"
        f"[dim]Content:[/dim] {content_dir}\n"
        f"[dim]Output:[/dim] {output_dir}\n\n"
        f"[dim]Next steps:[/dim]\n"
        f"1. cd {project_path}\n"
        f"2. scribe dev -c scribe.yml\n\n"
        f"Run [cyan]scribe dev -c scribe.yml[/cyan] to start the "
        f"development server.",
        title="Project Initialized",
        border_style="green",
    )
    console.print(panel)


@main.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to configuration file (defaults to ~/.scribe/config.yml)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be changed without making modifications",
)
def add_headers(config: Path | None, dry_run: bool) -> None:
    """Add stub frontmatter headers to markdown files that don't have them."""
    site_config = ScribeConfig(config_file=config)

    # Use source from config
    source_dir = site_config.source_dir

    if not source_dir.exists():
        console.print(f"[red]Error:[/red] Source directory {source_dir} does not exist")
        return

    # Find all markdown files
    markdown_files = []
    for pattern in ["*.md", "*.markdown"]:
        markdown_files.extend(source_dir.rglob(pattern))

    if not markdown_files:
        console.print(f"[yellow]No markdown files found in {source_dir}[/yellow]")
        return

    console.print(f"[blue]Scanning {len(markdown_files)} markdown files...[/blue]")

    files_without_headers = []
    files_with_headers = []

    for file_path in markdown_files:
        try:
            content = file_path.read_text(encoding="utf-8")

            # Check if file starts with frontmatter
            if content.strip().startswith("---"):
                # Look for closing frontmatter delimiter
                lines = content.split("\n")
                if len(lines) > 1:
                    # Find second occurrence of "---"
                    closing_found = False
                    for _i, line in enumerate(lines[1:], 1):
                        if line.strip() == "---":
                            closing_found = True
                            break

                    if closing_found:
                        files_with_headers.append(file_path)
                    else:
                        files_without_headers.append(file_path)
                else:
                    files_without_headers.append(file_path)
            else:
                files_without_headers.append(file_path)

        except Exception as e:
            console.print(f"[red]Error reading {file_path}:[/red] {e}")

    # Report findings
    console.print(
        f"[green]✓ {len(files_with_headers)} files already have headers[/green]"
    )
    console.print(f"[yellow]⚠ {len(files_without_headers)} files need headers[/yellow]")

    if not files_without_headers:
        console.print("[green]All files already have frontmatter headers![/green]")
        return

    if dry_run:
        console.print("\n[blue]Files that would be modified (--dry-run):[/blue]")
        for file_path in files_without_headers:
            relative_path = file_path.relative_to(source_dir)
            console.print(f"  • {relative_path}")
        console.print(
            f"\nRun without [cyan]--dry-run[/cyan] to add headers to "
            f"{len(files_without_headers)} files"
        )
        return

    # Add headers to files
    console.print(
        f"\n[blue]Adding headers to {len(files_without_headers)} files...[/blue]"
    )

    added_count = 0
    error_count = 0

    for file_path in files_without_headers:
        try:
            content = file_path.read_text(encoding="utf-8")
            relative_path = file_path.relative_to(source_dir)

            # Generate title from filename
            title = file_path.stem.replace("-", " ").replace("_", " ").title()

            # Create stub frontmatter
            stub_header = f"""---
title: {title}
description: ""
date: {time.strftime("%Y-%m-%d")}
tags: []
status: scratch
---

"""

            # Prepend header to existing content
            new_content = stub_header + content

            # Write back to file
            file_path.write_text(new_content, encoding="utf-8")

            console.print(f"[green]✓ Added header to:[/green] {relative_path}")
            added_count += 1

        except Exception as e:
            console.print(
                f"[red]Error processing {file_path.relative_to(source_dir)}:[/red] {e}"
            )
            error_count += 1

    # Summary
    if added_count > 0:
        console.print(
            f"\n[green]✓ Successfully added headers to {added_count} file(s)[/green]"
        )
    if error_count > 0:
        console.print(f"[red]✗ Failed to process {error_count} file(s)[/red]")


@main.command()
def config() -> None:
    """Show current configuration."""
    config = ScribeConfig()

    # Create a table for configuration display
    table = Table(title="Scribe Configuration", show_header=False)
    table.add_column("Setting", style="cyan", width=20)
    table.add_column("Value", style="white")

    # Add configuration rows
    table.add_row("Config file", str(config.config_dir / "config.yml"))
    table.add_row("Source directory", str(config.source_dir))
    table.add_row("Output directory", str(config.output_dir))
    table.add_row("Development server", f"{config.host}:{config.port}")
    table.add_row("Site title", config.site_title)
    table.add_row("Site description", config.site_description or "[dim]Not set[/dim]")
    table.add_row("Clean output", "✓" if config.clean_output else "✗")

    console.print(table)

    if config.note_plugins:
        console.print("\n[bold]Note Plugins:[/bold]")
        for plugin in config.note_plugins:
            status = (
                "[green]enabled[/green]" if plugin.enabled else "[red]disabled[/red]"
            )
            console.print(f"  • {plugin.name} ({status})")


if __name__ == "__main__":
    main()
