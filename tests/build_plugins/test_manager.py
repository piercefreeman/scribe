"""Test build plugin manager dependency resolution."""


from scribe.build_plugins.config import (
    BuildPluginName,
    TailwindBuildPluginConfig,
    TypeScriptBuildPluginConfig,
)
from scribe.build_plugins.manager import BuildPluginManager


class TestBuildPluginManagerDependencies:
    """Test build plugin manager dependency resolution."""

    def test_simple_dependency_resolution(self) -> None:
        """Test that build plugin dependencies are resolved correctly."""
        manager = BuildPluginManager()

        # tailwind depends on typescript
        tailwind_config = TailwindBuildPluginConfig(input="input.css")

        configs = [
            tailwind_config,
            TypeScriptBuildPluginConfig(source="src", output="js"),
        ]

        sorted_configs = manager._resolve_plugin_dependencies(configs)

        # typescript should come before tailwind
        plugin_names = [config.name for config in sorted_configs]
        assert plugin_names == [
            BuildPluginName.TAILWIND,
            BuildPluginName.TYPESCRIPT,
        ]
