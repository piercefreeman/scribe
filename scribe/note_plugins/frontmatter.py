"""Frontmatter plugin for extracting YAML metadata from markdown files."""

import logging

from frontmatter import loads as fm_loads
from pydantic_core import ValidationError

from scribe.context import FrontmatterData, PageContext
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import FrontmatterPluginConfig, PluginName

logger = logging.getLogger(__name__)


class FrontmatterPlugin(NotePlugin[FrontmatterPluginConfig]):
    """Plugin to extract frontmatter from markdown files."""

    name = PluginName.FRONTMATTER

    async def process(self, ctx: PageContext) -> PageContext:
        """Extract frontmatter and content from raw markdown."""
        post = fm_loads(ctx.raw_content)
        ctx.content = post.content

        # Validate and construct FrontmatterData from extracted metadata
        try:
            ctx.frontmatter = FrontmatterData(**post.metadata)
            logger.debug(f"Successfully validated frontmatter for {ctx.source_path}")
        except ValidationError as e:
            logger.error(f"Frontmatter validation error: {post.metadata}")
            raise e

        # Apply validated frontmatter data to context fields
        # (only if context field is not already set)
        if not ctx.title and ctx.frontmatter.title:
            ctx.title = ctx.frontmatter.title

        if not ctx.description and ctx.frontmatter.description:
            ctx.description = ctx.frontmatter.description

        if not ctx.tags and ctx.frontmatter.tags:
            ctx.tags = ctx.frontmatter.tags

        if not ctx.date and ctx.frontmatter.date:
            ctx.date = ctx.frontmatter.date

        if not ctx.featured_photos and ctx.frontmatter.featured_photos:
            ctx.featured_photos = ctx.frontmatter.featured_photos

        if not ctx.author and ctx.frontmatter.author:
            ctx.author = ctx.frontmatter.author

        if not ctx.external_link and ctx.frontmatter.external_link:
            ctx.external_link = ctx.frontmatter.external_link

        # Template and layout settings
        if (
            ctx.template == "default.html"
            and ctx.frontmatter.template != "default.html"
        ):
            ctx.template = ctx.frontmatter.template

        if not ctx.layout and ctx.frontmatter.layout:
            ctx.layout = ctx.frontmatter.layout

        # Status (always use frontmatter status as it's validated)
        ctx.status = ctx.frontmatter.status

        # If no title is found, try to extract from content
        if not ctx.title:
            try:
                ctx.title, ctx.content = ctx.extract_title_from_content()
            except ValueError:
                # If title extraction fails, that's okay - just leave title as None
                pass

        return ctx
