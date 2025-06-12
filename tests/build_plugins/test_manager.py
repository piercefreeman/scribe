"""Test build plugin manager dependency resolution."""

import pytest

from scribe.build_plugins.config import (
    BuildPluginName,
    TailwindBuildPluginConfig,
    TypeScriptBuildPluginConfig,
)
from scribe.build_plugins.manager import BuildPluginManager


class TestBuildPluginManagerDependencies:
    """Test build plugin manager dependency resolution."""

    def test_empty_dependencies_load_in_original_order(self) -> None:
        """Test that build plugins with no dependencies load in the order provided."""
        manager = BuildPluginManager()

        configs = [
            TypeScriptBuildPluginConfig(source="src", output="js"),
            TailwindBuildPluginConfig(input="input.css"),
        ]

        sorted_configs = manager._resolve_plugin_dependencies(configs)

        # With no dependencies, order should be preserved
        assert [config.name for config in sorted_configs] == ["typescript", "tailwind"]

    def test_simple_dependency_resolution(self) -> None:
        """Test that build plugin dependencies are resolved correctly."""
        manager = BuildPluginManager()

        # tailwind depends on typescript
        tailwind_config = TailwindBuildPluginConfig(input="input.css")
        tailwind_config.dependencies = [BuildPluginName.TYPESCRIPT]

        configs = [
            tailwind_config,
            TypeScriptBuildPluginConfig(source="src", output="js"),
        ]

        sorted_configs = manager._resolve_plugin_dependencies(configs)

        # typescript should come before tailwind
        plugin_names = [config.name for config in sorted_configs]
        assert plugin_names == ["typescript", "tailwind"]

    def test_missing_dependency_raises_error(self) -> None:
        """Test that missing build plugin dependencies raise an error."""
        manager = BuildPluginManager()

        # tailwind depends on typescript, but typescript is not in configs
        tailwind_config = TailwindBuildPluginConfig(input="input.css")
        tailwind_config.dependencies = [BuildPluginName.TYPESCRIPT]

        configs = [tailwind_config]

        with pytest.raises(
            ValueError, match="depends on 'typescript' which is not enabled"
        ):
            manager._resolve_plugin_dependencies(configs)

    def test_circular_dependency_raises_error(self) -> None:
        """Test that circular build plugin dependencies raise an error."""
        manager = BuildPluginManager()

        # Create circular dependency: typescript -> tailwind -> typescript
        typescript_config = TypeScriptBuildPluginConfig(source="src", output="js")
        typescript_config.dependencies = [BuildPluginName.TAILWIND]

        tailwind_config = TailwindBuildPluginConfig(input="input.css")
        tailwind_config.dependencies = [BuildPluginName.TYPESCRIPT]

        configs = [typescript_config, tailwind_config]

        with pytest.raises(ValueError, match="Circular dependency detected"):
            manager._resolve_plugin_dependencies(configs)

    def test_disabled_plugins_ignored_in_dependencies(self) -> None:
        """Test that disabled build plugins are ignored in dependency resolution."""
        manager = BuildPluginManager()

        # tailwind depends on typescript, but typescript is disabled
        tailwind_config = TailwindBuildPluginConfig(input="input.css")
        tailwind_config.dependencies = [BuildPluginName.TYPESCRIPT]

        typescript_config = TypeScriptBuildPluginConfig(source="src", output="js")
        typescript_config.enabled = False

        configs = [tailwind_config, typescript_config]

        with pytest.raises(
            ValueError, match="depends on 'typescript' which is not enabled"
        ):
            manager._resolve_plugin_dependencies(configs)

    def test_load_plugins_with_dependencies(self) -> None:
        """Test that build plugins are loaded in dependency-resolved order."""
        manager = BuildPluginManager()

        # tailwind depends on typescript
        tailwind_config = TailwindBuildPluginConfig(input="input.css")
        tailwind_config.dependencies = [BuildPluginName.TYPESCRIPT]

        configs = [
            tailwind_config,
            TypeScriptBuildPluginConfig(source="src", output="js"),
        ]

        manager.load_plugins_from_config(configs)

        # Should have 2 plugins loaded in correct order
        assert len(manager.plugins) == 2
        assert manager.plugins[0].name == "typescript"
        assert manager.plugins[1].name == "tailwind"
