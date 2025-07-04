"""Plugin system for Scribe."""

from .base import NotePlugin
from .date import DatePlugin
from .footnotes import FootnotesPlugin
from .frontmatter import FrontmatterPlugin
from .image_encoding import ImageEncodingPlugin
from .manager import PluginManager
from .markdown import MarkdownPlugin
from .screenshot import ScreenshotPlugin
from .snapshot import SnapshotPlugin

__all__ = [
    "NotePlugin",
    "PluginManager",
    "DatePlugin",
    "FootnotesPlugin",
    "FrontmatterPlugin",
    "ImageEncodingPlugin",
    "MarkdownPlugin",
    "ScreenshotPlugin",
    "SnapshotPlugin",
]
