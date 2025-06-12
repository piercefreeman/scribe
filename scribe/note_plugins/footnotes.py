"""Footnote reordering plugin for markdown files."""

import re

from scribe.context import PageContext
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import FootnotesPluginConfig, PluginName


class FootnotesPlugin(NotePlugin[FootnotesPluginConfig]):
    """Plugin to reorder footnotes in markdown content."""

    name = PluginName.FOOTNOTES

    def __init__(self, config: FootnotesPluginConfig) -> None:
        super().__init__(config)

        # Regex patterns for footnote references and definitions
        self.footnote_ref_pattern = re.compile(r"\[\^([^\]]+)\]")
        self.footnote_def_pattern = re.compile(r"^\[\^([^\]]+)\]: (.+)$", re.MULTILINE)

    async def process(self, ctx: PageContext) -> PageContext:
        """Reorder footnotes to be sequential 1-n."""
        content = ctx.content

        # Find all footnote references in order of appearance
        refs_in_order = []
        for match in self.footnote_ref_pattern.finditer(content):
            ref_id = match.group(1)
            if ref_id not in refs_in_order:
                refs_in_order.append(ref_id)

        # If no footnotes found, return unchanged
        if not refs_in_order:
            return ctx

        # Find all footnote definitions
        definitions = {}
        for match in self.footnote_def_pattern.finditer(content):
            def_id = match.group(1)
            def_text = match.group(2)
            definitions[def_id] = def_text

        # Create mapping from old IDs to new sequential numbers
        id_mapping = {}
        for i, old_id in enumerate(refs_in_order, 1):
            id_mapping[old_id] = str(i)

        # Replace footnote references in content
        def replace_ref(match):
            old_id = match.group(1)
            if old_id in id_mapping:
                return f"[^{id_mapping[old_id]}]"
            return match.group(0)  # Keep unchanged if not found

        content = self.footnote_ref_pattern.sub(replace_ref, content)

        # Remove old footnote definitions
        content = self.footnote_def_pattern.sub("", content)

        # Clean up extra newlines left by removing definitions
        content = re.sub(r"\n\n+", "\n\n", content)

        # Add reordered footnote definitions at the end
        if definitions:
            # Ensure proper spacing before footnotes
            if content.strip():
                if not content.endswith("\n\n"):
                    if content.endswith("\n"):
                        content += "\n"
                    else:
                        content += "\n\n"

            # Add footnotes in new order
            for old_id in refs_in_order:
                if old_id in definitions:
                    new_id = id_mapping[old_id]
                    content += f"[^{new_id}]: {definitions[old_id]}\n"

        ctx.content = content
        return ctx
