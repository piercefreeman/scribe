"""Base build plugin class for Scribe."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

from scribe.config import ScribeConfig

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

    @abstractmethod
    async def execute(self, site_config: ScribeConfig, output_dir: Path) -> None:
        """Execute the build plugin."""
        pass

    @abstractmethod
    def setup(self) -> None:
        """Setup hook called when plugin is loaded."""
        pass

    @abstractmethod
    def teardown(self) -> None:
        """Teardown hook called when plugin is unloaded."""
        pass
