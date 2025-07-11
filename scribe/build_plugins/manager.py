"""Build plugin manager for loading and executing build plugins."""

import time
from pathlib import Path

from scribe.build_plugins.base import BuildPlugin
from scribe.build_plugins.config import BuildPluginConfig, BuildPluginName
from scribe.build_plugins.link_resolution import LinkResolutionBuildPlugin
from scribe.build_plugins.tailwind import TailwindBuildPlugin
from scribe.build_plugins.typescript import TypeScriptBuildPlugin
from scribe.config import ScribeConfig
from scribe.context import PageContext
from scribe.logger import get_logger
from scribe.plugins import BasePluginManager

logger = get_logger(__name__)


class BuildPluginManager(BasePluginManager[BuildPluginConfig, BuildPlugin]):
    """Manages loading and execution of build plugins."""

    def __init__(self) -> None:
        super().__init__()
        self._plugin_registry: dict[BuildPluginName, type[BuildPlugin]] = {
            BuildPluginName.TAILWIND: TailwindBuildPlugin,
            BuildPluginName.TYPESCRIPT: TypeScriptBuildPlugin,
            BuildPluginName.LINK_RESOLUTION: LinkResolutionBuildPlugin,
        }

    def load_plugin(self, name: str, config: BuildPluginConfig) -> BuildPlugin:
        """Load and configure a build plugin."""
        if name not in self._plugin_registry:
            raise ValueError(f"Unknown build plugin: {name}")

        plugin_class = self._plugin_registry[name]
        plugin = plugin_class(config)
        plugin.setup()
        return plugin

    async def execute_before_notes(
        self, site_config: ScribeConfig, output_dir: Path
    ) -> None:
        """Execute before_notes phase for all loaded build plugins."""
        for plugin in self.plugins:
            start_time = time.perf_counter()
            await plugin.before_notes(site_config, output_dir)
            end_time = time.perf_counter()
            duration = end_time - start_time
            logger.info(f"Build plugin {plugin.name} before_notes took {duration:.4f}s")

    async def execute_after_notes(
        self, site_config: ScribeConfig, output_dir: Path, contexts: list[PageContext]
    ) -> list[PageContext]:
        """Execute after_notes phase for all loaded build plugins."""
        for plugin in self.plugins:
            start_time = time.perf_counter()
            contexts = await plugin.after_notes(site_config, output_dir, contexts)
            end_time = time.perf_counter()
            duration = end_time - start_time
            logger.info(f"Build plugin {plugin.name} after_notes took {duration:.4f}s")
        return contexts

    async def execute_after_all(
        self, site_config: ScribeConfig, output_dir: Path
    ) -> None:
        """Execute after_all phase for all loaded build plugins."""
        for plugin in self.plugins:
            start_time = time.perf_counter()
            await plugin.after_all(site_config, output_dir)
            end_time = time.perf_counter()
            duration = end_time - start_time
            logger.info(f"Build plugin {plugin.name} after_all took {duration:.4f}s")

    async def execute_plugins(
        self, site_config: ScribeConfig, output_dir: Path
    ) -> None:
        """Legacy execute method - calls after_all phase."""
        await self.execute_after_all(site_config, output_dir)
