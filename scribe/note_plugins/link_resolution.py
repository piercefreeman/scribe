"""Link resolution plugin for updating markdown page links to actual slugs."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

from scribe.context import PageContext
from scribe.logger import get_logger
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import LinkResolutionPluginConfig, PluginName

if TYPE_CHECKING:
    from scribe.config import ScribeConfig

logger = get_logger(__name__)


class LinkResolutionPlugin(NotePlugin[LinkResolutionPluginConfig]):
    """Plugin to resolve markdown page links to actual slug destinations."""

    name = PluginName.LINK_RESOLUTION

    def __init__(
        self, config: LinkResolutionPluginConfig, global_config: "ScribeConfig"
    ) -> None:
        super().__init__(config)
        self.global_config = global_config
        self._page_slug_map: dict[str, str] = {}
        self._page_slug_map_initialized = False

        # Regex pattern for markdown links: [text](url)
        self.markdown_link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

    async def process(self, ctx: PageContext) -> PageContext:
        """Process markdown content to resolve page links to actual slugs."""
        # Initialize the page slug map if not already done
        if not self._page_slug_map_initialized:
            self._build_page_slug_map()

        # Find and update markdown links
        ctx.content = self._resolve_links_in_content(ctx.content, ctx)

        return ctx

    def _build_page_slug_map(self) -> None:
        """Build a mapping of page paths/titles to their slugs."""
        if not self.global_config.source_dir.exists():
            self._page_slug_map_initialized = True
            return

        # Find all markdown files in the source directory
        markdown_files = []
        for pattern in ["*.md", "*.markdown"]:
            markdown_files.extend(self.global_config.source_dir.rglob(pattern))

        logger.debug(f"Found {len(markdown_files)} markdown files for link resolution")

        # Build mapping of various identifiers to slugs
        for file_path in markdown_files:
            try:
                relative_path = file_path.relative_to(self.global_config.source_dir)

                # Create a temporary context to extract slug information
                temp_ctx = self._create_temp_context(file_path, relative_path)

                # Map relative path (without extension) to slug
                relative_path_no_ext = str(relative_path.with_suffix(""))
                self._page_slug_map[relative_path_no_ext] = temp_ctx.slug or "untitled"

                # Map filename (without extension) to slug
                filename_no_ext = file_path.stem
                self._page_slug_map[filename_no_ext] = temp_ctx.slug or "untitled"

                # If we extracted a title, map title to slug as well
                if temp_ctx.title:
                    self._page_slug_map[temp_ctx.title] = temp_ctx.slug or "untitled"

                logger.debug(
                    f"Mapped page {relative_path_no_ext} -> slug: {temp_ctx.slug}"
                )

            except Exception as e:
                logger.warning(f"Error processing {file_path} for link resolution: {e}")

        self._page_slug_map_initialized = True
        logger.info(
            f"Built link resolution map with {len(self._page_slug_map)} entries"
        )

    def _create_temp_context(self, file_path: Path, relative_path: Path) -> PageContext:
        """Create a temporary page context to extract slug information."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            content = ""

        # Calculate output path (replace .md with .html)
        output_relative = relative_path.with_suffix(".html")
        output_path = self.global_config.output_dir / output_relative

        # Get file modification time
        try:
            modified_time = file_path.stat().st_mtime
        except Exception:
            modified_time = None

        # Create context - this will automatically generate slug from filename or title
        ctx = PageContext(
            source_path=file_path,
            relative_path=relative_path,
            output_path=output_path,
            raw_content=content,
            content=content,
            modified_time=modified_time,
        )

        # Try to extract title from content if available
        if not ctx.title and content:
            try:
                ctx.title, _ = ctx.extract_title_from_content()
            except ValueError:
                # Title extraction failed, that's okay
                pass

        return ctx

    def _resolve_links_in_content(self, content: str, ctx: PageContext) -> str:
        """Resolve markdown links in content to actual page slugs."""

        def replace_link(match):
            link_text = match.group(1)
            link_url = match.group(2)

            # Skip external links (http/https/mailto/etc)
            if self._is_external_link(link_url):
                return match.group(0)  # Return unchanged

            # Skip anchor links
            if link_url.startswith("#"):
                return match.group(0)  # Return unchanged

            # Try to resolve the link
            resolved_url = self._resolve_page_link(link_url, ctx)
            if resolved_url != link_url:
                logger.debug(f"Resolved link: {link_url} -> {resolved_url}")
                return f"[{link_text}]({resolved_url})"

            return match.group(0)  # Return unchanged if no resolution

        return self.markdown_link_pattern.sub(replace_link, content)

    def _is_external_link(self, url: str) -> bool:
        """Check if a URL is an external link."""
        return url.startswith(("http://", "https://", "mailto:", "ftp://", "//"))

    def _resolve_page_link(self, link_url: str, ctx: PageContext) -> str:
        """Resolve a page link to the actual slug-based URL."""
        # Clean up the link URL
        link_url = link_url.strip()

        # Remove .md extension if present
        if link_url.endswith(".md"):
            link_url = link_url[:-3]

        # Try direct lookup in our slug map
        if link_url in self._page_slug_map:
            slug = self._page_slug_map[link_url]
            return self._generate_url_from_slug(slug)

        # Try relative path resolution
        resolved_link = self._try_relative_path_resolution(link_url, ctx)
        if resolved_link:
            return resolved_link

        # If no resolution found, return original
        return link_url + (".md" if not self._is_external_link(link_url) else "")

    def _try_relative_path_resolution(
        self, link_url: str, ctx: PageContext
    ) -> str | None:
        """Try to resolve a link using relative path logic."""
        # Handle relative paths like ./other-page or ../other-page
        if link_url.startswith("./") or link_url.startswith("../"):
            try:
                # Get the directory of the current page
                current_dir = ctx.relative_path.parent

                # Resolve the relative path (but keep it as relative)
                target_path = current_dir / link_url

                # Normalize the path to remove . and .. components
                # Convert to string and back to Path to normalize
                normalized_path = str(target_path).replace("\\", "/")
                # Remove leading ./ if present
                if normalized_path.startswith("./"):
                    normalized_path = normalized_path[2:]

                # Try to find this path in our slug map
                if normalized_path in self._page_slug_map:
                    slug = self._page_slug_map[normalized_path]
                    return self._generate_url_from_slug(slug)

                # Also try just the filename without directory
                filename_only = Path(normalized_path).name
                if filename_only in self._page_slug_map:
                    slug = self._page_slug_map[filename_only]
                    return self._generate_url_from_slug(slug)

            except Exception as e:
                logger.debug(f"Error resolving relative path {link_url}: {e}")

        return None

    def _generate_url_from_slug(self, slug: str) -> str:
        """Generate URL from slug based on template configuration."""
        # For now, use a simple approach - if we have template configuration
        # we could make this more sophisticated
        if self.global_config.templates and self.global_config.templates.note_templates:
            # Use the first template's URL pattern as a guide
            for template in self.global_config.templates.note_templates:
                url_pattern = template.url_pattern
                if "{slug}" in url_pattern:
                    return url_pattern.replace("{slug}", slug)

        # Default: just use the slug with leading slash
        return f"/{slug}/"
