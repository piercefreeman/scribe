"""Markdown plugin for converting markdown to HTML."""

import markdown

from scribe.context import PageContext
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import MarkdownPluginConfig, PluginName


class MarkdownPlugin(NotePlugin[MarkdownPluginConfig]):
    """Plugin to convert markdown to HTML."""

    name = PluginName.MARKDOWN

    def __init__(self, config: MarkdownPluginConfig) -> None:
        super().__init__(config)

        # Configure markdown with common extensions
        extensions = [
            "markdown.extensions.fenced_code",
            "markdown.extensions.tables",
            "markdown.extensions.toc",
            "markdown.extensions.codehilite",
            "markdown.extensions.meta",
            "markdown.extensions.footnotes",
        ]

        self.md = markdown.Markdown(
            extensions=extensions,
            extension_configs={
                "codehilite": {"css_class": "highlight"},
                "toc": {"permalink": True},
            },
        )

    async def process(self, ctx: PageContext) -> PageContext:
        """Convert markdown content to HTML."""
        # Reset the markdown processor state to prevent footnote numbering
        # leakage between files
        self.md.reset()

        ctx.content = self.md.convert(ctx.content)

        # Extract metadata from markdown extensions
        if hasattr(self.md, "Meta"):
            for key, value in self.md.Meta.items():
                if key not in ctx.frontmatter:
                    ctx.frontmatter[key] = value[0] if len(value) == 1 else value

        return ctx
