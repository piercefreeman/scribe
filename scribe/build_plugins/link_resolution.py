"""Link resolution build plugin for updating markdown page links to actual slugs."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from scribe.build_plugins.base import BuildPlugin
from scribe.build_plugins.config import LinkResolutionBuildPluginConfig
from scribe.config import ScribeConfig
from scribe.context import PageContext
from scribe.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class LinkResolutionBuildPlugin(BuildPlugin[LinkResolutionBuildPluginConfig]):
    """Build plugin to resolve markdown page links to actual slug destinations."""

    def __init__(self, config: LinkResolutionBuildPluginConfig) -> None:
        super().__init__(config)
        self.name = "link_resolution"  # Explicitly set the name
        # Regex pattern for markdown links: [text](url)
        self.markdown_link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

    async def after_notes(
        self, site_config: ScribeConfig, output_dir: Path, contexts: list[PageContext]
    ) -> list[PageContext]:
        """Process all notes to resolve page links to actual slugs."""
        # Build a mapping of page identifiers to their final URLs
        page_slug_map = self._build_page_slug_map(contexts, site_config)

        logger.info(f"Built link resolution map with {len(page_slug_map)} entries")

        # Process each context to resolve links
        for ctx in contexts:
            ctx.content = self._resolve_links_in_content(
                ctx.content, ctx, page_slug_map
            )

        return contexts

    def _build_page_slug_map(
        self, contexts: list[PageContext], site_config: ScribeConfig
    ) -> dict[str, str]:
        """Build a mapping of page paths/titles to their final URLs."""
        page_slug_map: dict[str, str] = {}

        for ctx in contexts:
            # Get the final URL for this context
            final_url = self._get_final_url_for_context(ctx, site_config)

            # Map relative path (without extension) to final URL
            relative_path_no_ext = str(ctx.relative_path.with_suffix(""))
            page_slug_map[relative_path_no_ext] = final_url

            # Map filename (without extension) to final URL
            filename_no_ext = ctx.source_path.stem
            page_slug_map[filename_no_ext] = final_url

            # If we have a title, map title to final URL as well
            if ctx.title:
                page_slug_map[ctx.title] = final_url

            logger.debug(f"Mapped page {relative_path_no_ext} -> {final_url}")

        return page_slug_map

    def _get_final_url_for_context(
        self, ctx: PageContext, site_config: ScribeConfig
    ) -> str:
        """Get the final URL for a context based on template configuration."""
        if not site_config.templates or not site_config.templates.note_templates:
            # Default: use the slug with leading slash
            return f"/{ctx.slug}/"

        # Find the matching template for this context
        for template in site_config.templates.note_templates:
            if self._note_matches_template(ctx, template, site_config):
                url_pattern = template.url_pattern
                if "{slug}" in url_pattern:
                    return url_pattern.replace("{slug}", ctx.slug or "untitled")

        # Default: use the slug with leading slash
        return f"/{ctx.slug}/"

    def _note_matches_template(
        self, ctx: PageContext, template, site_config: ScribeConfig
    ) -> bool:
        """Check if a note context matches a template's predicates."""
        # If no predicates, match all
        if not template.predicates:
            return True

        # Import the predicate matcher to do proper matching
        from scribe.predicates import PredicateMatcher

        predicate_matcher = PredicateMatcher()
        return predicate_matcher.matches_predicates(ctx, tuple(template.predicates))

    def _resolve_links_in_content(
        self, content: str, ctx: PageContext, page_slug_map: dict[str, str]
    ) -> str:
        """Resolve markdown and HTML links in content to actual page URLs."""

        # First, resolve any remaining markdown links
        def replace_markdown_link(match):
            link_text = match.group(1)
            link_url = match.group(2)

            # Skip external links (http/https/mailto/etc)
            if self._is_external_link(link_url):
                return match.group(0)  # Return unchanged

            # Skip anchor links
            if link_url.startswith("#"):
                return match.group(0)  # Return unchanged

            # Try to resolve the link
            resolved_url = self._resolve_page_link(link_url, ctx, page_slug_map)
            if resolved_url != link_url:
                logger.debug(f"Resolved markdown link: {link_url} -> {resolved_url}")
                return f"[{link_text}]({resolved_url})"

            return match.group(0)  # Return unchanged if no resolution

        content = self.markdown_link_pattern.sub(replace_markdown_link, content)

        # Then, parse and resolve HTML links using Beautiful Soup
        content = self._resolve_html_links(content, ctx, page_slug_map)

        return content

    def _resolve_html_links(
        self, content: str, ctx: PageContext, page_slug_map: dict[str, str]
    ) -> str:
        """Resolve HTML links using Beautiful Soup for proper parsing."""
        try:
            # Parse the HTML content
            soup = BeautifulSoup(content, "html.parser")

            # Find all anchor tags with href attributes
            for link in soup.find_all("a", href=True):
                href = link["href"]

                # Skip external links (http/https/mailto/etc)
                if self._is_external_link(href):
                    continue

                # Skip anchor links
                if href.startswith("#"):
                    continue

                # Try to resolve the link
                resolved_url = self._resolve_page_link(href, ctx, page_slug_map)
                if resolved_url != href:
                    logger.debug(f"Resolved HTML link: {href} -> {resolved_url}")
                    link["href"] = resolved_url

            # Return the modified HTML
            return str(soup)

        except Exception as e:
            logger.warning(f"Error parsing HTML content for link resolution: {e}")
            # Fall back to returning original content if parsing fails
            return content

    def _is_external_link(self, url: str) -> bool:
        """Check if a URL is an external link."""
        return url.startswith(("http://", "https://", "mailto:", "ftp://", "//"))

    def _resolve_page_link(
        self, link_url: str, ctx: PageContext, page_slug_map: dict[str, str]
    ) -> str:
        """Resolve a page link to the actual URL."""
        # Clean up the link URL
        link_url = link_url.strip()

        # Remove .md extension if present
        if link_url.endswith(".md"):
            link_url = link_url[:-3]

        # Try direct lookup in our slug map
        if link_url in page_slug_map:
            return page_slug_map[link_url]

        # Try relative path resolution
        resolved_link = self._try_relative_path_resolution(link_url, ctx, page_slug_map)
        if resolved_link:
            return resolved_link

        # If no resolution found, return original (or add .md back if it was removed)
        return link_url + (".md" if not self._is_external_link(link_url) else "")

    def _try_relative_path_resolution(
        self, link_url: str, ctx: PageContext, page_slug_map: dict[str, str]
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
                if normalized_path in page_slug_map:
                    return page_slug_map[normalized_path]

                # Also try just the filename without directory
                filename_only = Path(normalized_path).name
                if filename_only in page_slug_map:
                    return page_slug_map[filename_only]

            except Exception as e:
                logger.debug(f"Error resolving relative path {link_url}: {e}")

        return None
