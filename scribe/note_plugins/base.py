"""Base plugin class for Scribe."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from scribe.context import PageContext
from scribe.note_plugins.config import PluginName

ConfigT = TypeVar("ConfigT")


class NotePlugin(ABC, Generic[ConfigT]):
    """Base class for all Scribe plugins."""

    name: PluginName

    def __init__(self, config: ConfigT) -> None:
        """Initialize plugin with configuration."""
        self.config = config

    @abstractmethod
    async def process(self, ctx: PageContext) -> PageContext:
        """Process a page context and return the modified context."""
        pass

    def setup(self) -> None:
        """Setup hook called when plugin is loaded."""
        pass

    def teardown(self) -> None:
        """Teardown hook called when plugin is unloaded."""
        pass
