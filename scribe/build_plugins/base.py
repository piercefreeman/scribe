"""Base build plugin class for Scribe."""

from abc import ABC
from pathlib import Path
from typing import Generic, TypeVar

from scribe.config import ScribeConfig
from scribe.context import PageContext

ConfigT = TypeVar("ConfigT")


class BuildPlugin(ABC, Generic[ConfigT]):
    """Base class for all build plugins."""

    def __init__(self, config: ConfigT) -> None:
        """Initialize build plugin with configuration."""
        self.config = config
        self.name = (
            self.__class__.__name__.lower()
            .replace("buildplugin", "")
            .replace("plugin", "")
        )

    async def before_notes(self, site_config: ScribeConfig, output_dir: Path) -> None:
        """Execute before any notes are processed."""
        pass

    async def after_notes(
        self, site_config: ScribeConfig, output_dir: Path, contexts: list[PageContext]
    ) -> list[PageContext]:
        """Execute after all notes are processed but before writing to disk.

        Can modify and return the list of contexts.
        """
        return contexts

    async def after_all(self, site_config: ScribeConfig, output_dir: Path) -> None:
        """Execute after all notes are written to disk."""
        pass

    async def execute(self, site_config: ScribeConfig, output_dir: Path) -> None:
        """Legacy execute method - calls after_all by default."""
        await self.after_all(site_config, output_dir)

    def setup(self) -> None:
        """Setup hook called when plugin is loaded."""
        pass

    def teardown(self) -> None:
        """Teardown hook called when plugin is unloaded."""
        pass
