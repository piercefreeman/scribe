"""Link resolution build plugin for updating markdown page links to actual slugs."""

from dataclasses import dataclass
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


@dataclass
class PageLink:
    """Represents a link found in page content."""

    url: str
    text: str = ""

    def is_external(self) -> bool:
        """Check if this is an external link."""
        return self.url.startswith(("http://", "https://", "mailto:", "ftp://", "//"))

    def is_anchor(self) -> bool:
        """Check if this is an anchor link."""
        return self.url.startswith("#")

    def should_resolve(self) -> bool:
        """Check if this link should be resolved."""
        return not self.is_external() and not self.is_anchor()


class UrlBuilder:
    """Builds final URLs for page contexts based on site configuration."""

    def build_url(self, ctx: PageContext, site_config: ScribeConfig) -> str:
        """Build the final URL for a page context."""
        if not site_config.templates or not site_config.templates.note_templates:
            return f"/{ctx.slug}/"

        # Find matching template
        for template in site_config.templates.note_templates:
            if self._matches_template(ctx, template, site_config):
                url_pattern = template.url_pattern
                if "{slug}" in url_pattern:
                    return url_pattern.replace("{slug}", ctx.slug or "untitled")

        return f"/{ctx.slug}/"

    def _matches_template(
        self, ctx: PageContext, template, site_config: ScribeConfig
    ) -> bool:
        """Check if a context matches a template's predicates."""
        if not template.predicates:
            return True

        from scribe.predicates import PredicateMatcher

        predicate_matcher = PredicateMatcher()
        return predicate_matcher.matches_predicates(ctx, tuple(template.predicates))


class LinkResolver:
    """Resolves page links to actual URLs using multiple strategies."""

    def __init__(self, slug_map: dict[str, str]) -> None:
        self.slug_map = slug_map

    def resolve(self, link: PageLink, ctx: PageContext) -> str:
        """Resolve a page link to its final URL."""
        if not link.should_resolve():
            return link.url

        original_url = link.url.strip()
        was_md_link = original_url.endswith(".md")
        cleaned_url = self._clean_url(link.url)

        # Try different resolution strategies in order
        strategies = [
            self._direct_lookup,
            self._relative_path_resolution,
        ]

        for strategy in strategies:
            resolved_url = strategy(cleaned_url, ctx)
            if resolved_url:
                return resolved_url

        # If original link was a .md file but we couldn't resolve it,
        # check if file exists
        if was_md_link:
            self._check_md_file_exists(original_url, ctx)

        # No resolution found - return original or with .md extension
        return cleaned_url + (".md" if not link.is_external() else "")

    def _clean_url(self, url: str) -> str:
        """Clean and normalize a URL."""
        url = url.strip()
        if url.endswith(".md"):
            url = url[:-3]
        return url

    def _direct_lookup(self, url: str, ctx: PageContext) -> str | None:
        """Try direct lookup in slug map."""
        return self.slug_map.get(url)

    def _relative_path_resolution(self, url: str, ctx: PageContext) -> str | None:
        """Try relative path resolution."""
        if not (url.startswith("./") or url.startswith("../")):
            return None

        try:
            current_dir = ctx.relative_path.parent
            target_path = current_dir / url
            normalized_path = str(target_path).replace("\\", "/")

            if normalized_path.startswith("./"):
                normalized_path = normalized_path[2:]

            # Try full path first
            resolved_url = self.slug_map.get(normalized_path)
            if resolved_url:
                return resolved_url

            # Try just filename
            filename_only = Path(normalized_path).name
            return self.slug_map.get(filename_only)

        except Exception as e:
            logger.debug(f"Error resolving relative path {url}: {e}")
            return None

    def _check_md_file_exists(self, original_url: str, ctx: PageContext) -> None:
        """Check if a .md file exists on disk and raise exception if not."""
        try:
            # Handle different types of paths
            if original_url.startswith("./") or original_url.startswith("../"):
                # Relative path
                current_dir = ctx.source_path.parent
                target_path = current_dir / original_url
                resolved_path = target_path.resolve()
            else:
                # Assume it's relative to the current file's directory
                current_dir = ctx.source_path.parent
                target_path = current_dir / original_url
                resolved_path = target_path.resolve()

            if not resolved_path.exists():
                raise FileNotFoundError(
                    f"Markdown file not found: '{original_url}' "
                    f"referenced in '{ctx.source_path}'. "
                    f"Resolved path: '{resolved_path}'"
                )

        except Exception as e:
            if isinstance(e, FileNotFoundError):
                raise
            # For other exceptions, still raise a meaningful error
            raise FileNotFoundError(
                f"Error checking markdown file: '{original_url}' "
                f"referenced in '{ctx.source_path}'. "
                f"Error: {e}"
            ) from e


class HtmlLinkProcessor:
    """Processes HTML anchor tags with href attributes."""

    def __init__(self, resolver: LinkResolver) -> None:
        self.resolver = resolver

    def process(self, content: str, ctx: PageContext) -> str:
        """Process HTML links in content."""
        try:
            soup = BeautifulSoup(content, "html.parser")

            for anchor in soup.find_all("a", href=True):
                href = anchor["href"]
                link = PageLink(url=href)
                resolved_url = self.resolver.resolve(link, ctx)

                if resolved_url != href:
                    logger.debug(f"Resolved HTML link: {href} -> {resolved_url}")
                    anchor["href"] = resolved_url

            return str(soup)

        except Exception as e:
            logger.warning(f"Error parsing HTML content for link resolution: {e}")
            return content


class PageSlugMapBuilder:
    """Builds the slug mapping from page contexts."""

    def __init__(self, url_builder: UrlBuilder) -> None:
        self.url_builder = url_builder

    def build(
        self, contexts: list[PageContext], site_config: ScribeConfig
    ) -> dict[str, str]:
        """Build a slug map from page contexts."""
        slug_map: dict[str, str] = {}

        for ctx in contexts:
            final_url = self.url_builder.build_url(ctx, site_config)

            # Add different mappings for the same URL
            mappings = self._get_mappings_for_context(ctx)
            for mapping in mappings:
                slug_map[mapping] = final_url

            logger.debug(
                f"Mapped page {ctx.relative_path.with_suffix('')} -> {final_url}"
            )

        return slug_map

    def _get_mappings_for_context(self, ctx: PageContext) -> list[str]:
        """Get all possible mappings for a context."""
        mappings = []

        # Relative path without extension
        relative_path_no_ext = str(ctx.relative_path.with_suffix(""))
        mappings.append(relative_path_no_ext)

        # Filename without extension
        filename_no_ext = ctx.source_path.stem
        mappings.append(filename_no_ext)

        # Title if available
        if ctx.title:
            mappings.append(ctx.title)

        return mappings


class LinkResolutionBuildPlugin(BuildPlugin[LinkResolutionBuildPluginConfig]):
    """Build plugin to resolve HTML page links to actual slug destinations."""

    def __init__(self, config: LinkResolutionBuildPluginConfig) -> None:
        super().__init__(config)
        self.name = "link_resolution"

    async def after_notes(
        self, site_config: ScribeConfig, output_dir: Path, contexts: list[PageContext]
    ) -> list[PageContext]:
        """Process all notes to resolve page links to actual slugs."""
        # Build the slug mapping
        url_builder = UrlBuilder()
        slug_map_builder = PageSlugMapBuilder(url_builder)
        slug_map = slug_map_builder.build(contexts, site_config)

        logger.info(f"Built link resolution map with {len(slug_map)} entries")

        # Set up link processing
        resolver = LinkResolver(slug_map)
        processor = HtmlLinkProcessor(resolver)

        # Process each context
        for ctx in contexts:
            ctx.content = processor.process(ctx.content, ctx)

        return contexts
