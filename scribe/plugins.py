"""Shared plugin infrastructure and abstract base classes."""

from abc import ABC, abstractmethod
from enum import Enum
from graphlib import TopologicalSorter
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from scribe.logger import get_logger

logger = get_logger(__name__)

# Type variables for generic classes
ConfigT = TypeVar("ConfigT")
PluginT = TypeVar("PluginT")
PluginNameT = TypeVar("PluginNameT", bound=Enum)


class PluginNameEnum(str, Enum):
    """Base class for plugin name enums."""

    pass


class BasePluginConfig(BaseModel, Generic[PluginNameT]):
    """Base configuration for all plugins."""

    enabled: bool = True
    after_dependencies: list[PluginNameT] = Field(
        default_factory=list,
        description="List of plugins that must run before this plugin",
    )
    before_dependencies: list[PluginNameT] = Field(
        default_factory=list,
        description="List of plugins that must run after this plugin",
    )


class BasePluginManager(ABC, Generic[ConfigT, PluginT]):
    """Base class for plugin managers with dependency resolution."""

    def __init__(self) -> None:
        self.plugins: list[PluginT] = []
        self._plugin_registry: dict[str, type[PluginT]] = {}

    @abstractmethod
    def load_plugin(self, name: str, config: ConfigT) -> PluginT:
        """Load and configure a plugin."""
        pass

    def register_plugin(self, name: str, plugin_class: type[PluginT]) -> None:
        """Register a custom plugin class."""
        self._plugin_registry[name] = plugin_class

    def _resolve_plugin_dependencies(
        self, plugin_configs: list[ConfigT]
    ) -> list[ConfigT]:
        """Resolve plugin dependencies using topological sorting."""
        # Create a mapping of plugin names to their configs
        plugin_config_map = {
            config.name: config for config in plugin_configs if config.enabled
        }

        # Check that all dependencies exist in the enabled plugins
        for config in plugin_config_map.values():
            for dep in config.after_dependencies:
                if dep.value not in plugin_config_map:
                    raise ValueError(
                        f"Plugin '{config.name}' has after_dependency on '{dep.value}' "
                        f"which is not enabled or doesn't exist"
                    )
            for dep in config.before_dependencies:
                if dep.value not in plugin_config_map:
                    raise ValueError(
                        f"Plugin '{config.name}' has before_dependency on "
                        f"'{dep.value}' which is not enabled or doesn't exist"
                    )

        # Build dependency graph
        graph: dict[str, set[str]] = {}
        for config in plugin_config_map.values():
            # Initialize with after_dependencies (plugins that must run before this one)
            graph[config.name] = {dep.value for dep in config.after_dependencies}

            # Add reverse dependencies from before_dependencies
            for dep in config.before_dependencies:
                dep_name = dep.value
                if dep_name not in graph:
                    graph[dep_name] = set()
                graph[dep_name].add(config.name)

        # Use TopologicalSorter to resolve dependencies
        try:
            sorter = TopologicalSorter(graph)
            sorted_plugin_names = list(sorter.static_order())
        except ValueError as e:
            plugin_type = self.__class__.__name__.replace("Manager", "").lower()
            raise ValueError(
                f"Circular dependency detected in {plugin_type} plugins: {e}"
            ) from e

        # Return configs in dependency-resolved order
        return [plugin_config_map[name] for name in sorted_plugin_names]

    def load_plugins_from_config(self, plugin_configs: list[ConfigT]) -> None:
        """Load plugins from config in dependency-resolved order."""
        # Only include enabled plugins
        enabled_configs = [config for config in plugin_configs if config.enabled]

        # Resolve dependencies and get sorted order
        sorted_configs = self._resolve_plugin_dependencies(enabled_configs)

        plugin_names = [config.name for config in sorted_configs]
        plugin_type = self.__class__.__name__.replace("Manager", "").lower()
        logger.info(
            f"Loading {plugin_type} plugins in dependency-resolved order: "
            f"{plugin_names}"
        )

        # Load plugins in resolved order
        for plugin_config in sorted_configs:
            plugin = self.load_plugin(plugin_config.name, plugin_config)
            self.plugins.append(plugin)

    def teardown(self) -> None:
        """Teardown all loaded plugins."""
        for plugin in self.plugins:
            plugin.teardown()
        self.plugins.clear()
