"""Plugin manager for loading and executing plugins."""

import inspect
import time
from pathlib import Path
from typing import TYPE_CHECKING

from scribe.context import PageContext
from scribe.logger import get_logger
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import PluginConfig, PluginName
from scribe.note_plugins.date import DatePlugin
from scribe.note_plugins.footnotes import FootnotesPlugin
from scribe.note_plugins.frontmatter import FrontmatterPlugin
from scribe.note_plugins.image_encoding import ImageEncodingPlugin
from scribe.note_plugins.markdown import MarkdownPlugin
from scribe.note_plugins.screenshot import ScreenshotPlugin
from scribe.note_plugins.snapshot import SnapshotPlugin
from scribe.plugins import BasePluginManager

if TYPE_CHECKING:
    from scribe.config import ScribeConfig

logger = get_logger(__name__)


class PluginManager(BasePluginManager[PluginConfig, NotePlugin]):
    """Manages loading and execution of plugins."""

    name: PluginName

    def __init__(self, global_config: "ScribeConfig | None" = None) -> None:
        super().__init__()
        self.global_config = global_config
        self._plugin_registry: dict[PluginName, type[NotePlugin]] = {
            PluginName.FRONTMATTER: FrontmatterPlugin,
            PluginName.FOOTNOTES: FootnotesPlugin,
            PluginName.MARKDOWN: MarkdownPlugin,
            PluginName.DATE: DatePlugin,
            PluginName.SCREENSHOT: ScreenshotPlugin,
            PluginName.SNAPSHOT: SnapshotPlugin,
            PluginName.IMAGE_ENCODING: ImageEncodingPlugin,
        }

    def load_plugin(self, name: str, config: PluginConfig) -> NotePlugin:
        """Load and configure a plugin."""
        if name not in self._plugin_registry:
            raise ValueError(f"Unknown plugin: {name}")

        plugin_class = self._plugin_registry[name]

        # Inspect the plugin constructor to determine what parameters it needs
        constructor_params = self._get_constructor_params(plugin_class, config)

        plugin = plugin_class(**constructor_params)
        plugin.setup()
        return plugin

    def _get_constructor_params(
        self, plugin_class: type[NotePlugin], config: PluginConfig
    ) -> dict[str, any]:
        """Inspect the plugin constructor and determine what parameters to provide.

        Uses simple name-based conventions:
        - 'config': gets the plugin config
        - 'global_config': gets the global ScribeConfig (if available)
        - other params with defaults: skipped
        - other required params: error

        """
        signature = inspect.signature(plugin_class.__init__)
        params = {}

        for param_name, param in signature.parameters.items():
            # Skip 'self' parameter
            if param_name == "self":
                continue

            if param_name == "config":
                # Plugin config parameter
                params[param_name] = config
            elif param_name == "global_config":
                # Global ScribeConfig parameter
                if self.global_config is not None:
                    params[param_name] = self.global_config
                elif param.default is not inspect.Parameter.empty:
                    # Has a default value, don't provide it
                    continue
                else:
                    # Required but we don't have it
                    raise ValueError(
                        f"Plugin {plugin_class.__name__} requires global_config "
                        f"but none provided"
                    )
            elif param.default is not inspect.Parameter.empty:
                # Has a default value, don't provide it
                continue
            else:
                # Unknown required parameter
                raise ValueError(
                    f"Unknown required parameter '{param_name}' for plugin "
                    f"{plugin_class.__name__}"
                )

        return params

    async def process_page(self, ctx: PageContext) -> PageContext:
        """Process a page through all loaded plugins."""
        for plugin in self.plugins:
            start_time = time.perf_counter()
            ctx = await plugin.process(ctx)
            end_time = time.perf_counter()
            duration = end_time - start_time
            logger.info(f"Plugin {plugin.name} took {duration:.4f}s")
        return ctx

    def get_plugin_by_name(self, name: PluginName) -> NotePlugin | None:
        """Get a loaded plugin by its name."""
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None

    def copy_snapshot_outputs(self, output_dir: Path) -> None:
        """Copy snapshots to output directory if snapshot plugin is loaded."""
        from scribe.note_plugins.snapshot import SnapshotPlugin

        snapshot_plugin = self.get_plugin_by_name(PluginName.SNAPSHOT)
        if isinstance(snapshot_plugin, SnapshotPlugin):
            snapshot_plugin.copy_snapshots_to_output(output_dir)
