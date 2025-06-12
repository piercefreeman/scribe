"""Test plugin manager dependency resolution."""

from unittest.mock import Mock

import pytest

from scribe.note_plugins.config import (
    DatePluginConfig,
    FootnotesPluginConfig,
    FrontmatterPluginConfig,
    ImageEncodingPluginConfig,
    MarkdownPluginConfig,
    PluginName,
)
from scribe.note_plugins.manager import PluginManager


class TestPluginManagerDependencies:
    """Test plugin manager dependency resolution."""

    def test_empty_dependencies_load_in_original_order(self) -> None:
        """Test that plugins with no dependencies load in the order provided."""
        manager = PluginManager()

        configs = [
            MarkdownPluginConfig(),
            FrontmatterPluginConfig(),
            DatePluginConfig(),
        ]

        sorted_configs = manager._resolve_plugin_dependencies(configs)

        # With no dependencies, order should be preserved
        assert [config.name for config in sorted_configs] == [
            "markdown",
            "frontmatter",
            "date",
        ]

    def test_simple_dependency_resolution(self) -> None:
        """Test that dependencies are resolved correctly."""
        manager = PluginManager()

        # markdown depends on frontmatter
        markdown_config = MarkdownPluginConfig()
        markdown_config.dependencies = [PluginName.FRONTMATTER]

        configs = [
            markdown_config,
            FrontmatterPluginConfig(),
            DatePluginConfig(),
        ]

        sorted_configs = manager._resolve_plugin_dependencies(configs)

        # frontmatter should come before markdown
        plugin_names = [config.name for config in sorted_configs]
        assert plugin_names.index("frontmatter") < plugin_names.index("markdown")
        assert "date" in plugin_names

    def test_multiple_dependencies(self) -> None:
        """Test resolution with multiple dependencies."""
        manager = PluginManager()

        # markdown depends on both frontmatter and date
        markdown_config = MarkdownPluginConfig()
        markdown_config.dependencies = [PluginName.FRONTMATTER, PluginName.DATE]

        configs = [
            markdown_config,
            FrontmatterPluginConfig(),
            DatePluginConfig(),
        ]

        sorted_configs = manager._resolve_plugin_dependencies(configs)

        plugin_names = [config.name for config in sorted_configs]

        # Both frontmatter and date should come before markdown
        assert plugin_names.index("frontmatter") < plugin_names.index("markdown")
        assert plugin_names.index("date") < plugin_names.index("markdown")

    def test_chain_dependencies(self) -> None:
        """Test resolution with chained dependencies."""
        manager = PluginManager()

        # footnotes depends on markdown, markdown depends on frontmatter
        footnotes_config = FootnotesPluginConfig()
        footnotes_config.dependencies = [PluginName.MARKDOWN]

        markdown_config = MarkdownPluginConfig()
        markdown_config.dependencies = [PluginName.FRONTMATTER]

        configs = [
            footnotes_config,
            markdown_config,
            FrontmatterPluginConfig(),
        ]

        sorted_configs = manager._resolve_plugin_dependencies(configs)

        plugin_names = [config.name for config in sorted_configs]

        # Should be in order: frontmatter -> markdown -> footnotes
        assert plugin_names == ["frontmatter", "markdown", "footnotes"]

    def test_missing_dependency_raises_error(self) -> None:
        """Test that missing dependencies raise an error."""
        manager = PluginManager()

        # markdown depends on frontmatter, but frontmatter is not in configs
        markdown_config = MarkdownPluginConfig()
        markdown_config.dependencies = [PluginName.FRONTMATTER]

        configs = [markdown_config]

        with pytest.raises(
            ValueError, match="depends on 'frontmatter' which is not enabled"
        ):
            manager._resolve_plugin_dependencies(configs)

    def test_circular_dependency_raises_error(self) -> None:
        """Test that circular dependencies raise an error."""
        manager = PluginManager()

        # Create circular dependency: markdown -> frontmatter -> markdown
        markdown_config = MarkdownPluginConfig()
        markdown_config.dependencies = [PluginName.FRONTMATTER]

        frontmatter_config = FrontmatterPluginConfig()
        frontmatter_config.dependencies = [PluginName.MARKDOWN]

        configs = [markdown_config, frontmatter_config]

        with pytest.raises(ValueError, match="Circular dependency detected"):
            manager._resolve_plugin_dependencies(configs)

    def test_disabled_plugins_ignored_in_dependencies(self) -> None:
        """Test that disabled plugins are ignored in dependency resolution."""
        manager = PluginManager()

        # markdown depends on frontmatter, but frontmatter is disabled
        markdown_config = MarkdownPluginConfig()
        markdown_config.dependencies = [PluginName.FRONTMATTER]

        frontmatter_config = FrontmatterPluginConfig()
        frontmatter_config.enabled = False

        configs = [markdown_config, frontmatter_config]

        with pytest.raises(
            ValueError, match="depends on 'frontmatter' which is not enabled"
        ):
            manager._resolve_plugin_dependencies(configs)

    def test_load_plugins_with_dependencies(self) -> None:
        """Test that plugins are loaded in dependency-resolved order."""
        manager = PluginManager()

        # markdown depends on frontmatter
        markdown_config = MarkdownPluginConfig()
        markdown_config.dependencies = [PluginName.FRONTMATTER]

        configs = [
            markdown_config,
            FrontmatterPluginConfig(),
        ]

        manager.load_plugins_from_config(configs)

        # Should have 2 plugins loaded in correct order
        assert len(manager.plugins) == 2
        assert manager.plugins[0].name == "frontmatter"
        assert manager.plugins[1].name == "markdown"


class TestPluginManagerConstructorParams:
    """Test plugin manager constructor parameter resolution."""

    def test_simple_config_only_plugin(self) -> None:
        """Test plugin that only takes config parameter."""
        from scribe.note_plugins.frontmatter import FrontmatterPlugin

        manager = PluginManager()
        config = FrontmatterPluginConfig()

        params = manager._get_constructor_params(FrontmatterPlugin, config)

        assert params == {"config": config}

    def test_config_with_scribe_config_plugin_no_global_config(self) -> None:
        """Test plugin with required global_config param when no global config."""
        from scribe.note_plugins.image_encoding import ImageEncodingPlugin

        manager = PluginManager()
        config = ImageEncodingPluginConfig()

        # Should raise error since global_config is now required
        with pytest.raises(
            ValueError,
            match="Plugin ImageEncodingPlugin requires global_config but none provided",
        ):
            manager._get_constructor_params(ImageEncodingPlugin, config)

    def test_config_with_scribe_config_plugin_with_global_config(self) -> None:
        """Test plugin with ScribeConfig param when global config is provided."""
        from scribe.note_plugins.image_encoding import ImageEncodingPlugin

        mock_global_config = Mock()
        manager = PluginManager(global_config=mock_global_config)
        config = ImageEncodingPluginConfig()

        params = manager._get_constructor_params(ImageEncodingPlugin, config)

        assert params == {"config": config, "global_config": mock_global_config}

    def test_plugin_with_optional_global_config(self) -> None:
        """Test plugin with optional global_config parameter."""

        # Create a mock plugin class that has an optional global_config parameter
        class MockPlugin:
            def __init__(self, config, global_config=None):
                pass

        manager = PluginManager()
        config = FrontmatterPluginConfig()

        params = manager._get_constructor_params(MockPlugin, config)

        # Should only include config since global_config has default value
        assert params == {"config": config}

    def test_required_global_config_plugin_no_global_config(self) -> None:
        """Test plugin with required global_config param when no global config."""

        # Create a mock plugin class that requires global_config (no default value)
        class MockPluginRequiresGlobalConfig:
            def __init__(self, config, global_config):
                pass

        manager = PluginManager()
        config = FrontmatterPluginConfig()

        with pytest.raises(
            ValueError,
            match="Plugin MockPluginRequiresGlobalConfig requires global_config "
            "but none provided",
        ):
            manager._get_constructor_params(MockPluginRequiresGlobalConfig, config)

    def test_unknown_required_parameter(self) -> None:
        """Test plugin with unknown required parameter raises error."""

        # Create a mock plugin class with unknown required parameter
        class MockPlugin:
            def __init__(self, config, unknown_param):
                pass

        manager = PluginManager()
        config = FrontmatterPluginConfig()

        with pytest.raises(
            ValueError,
            match="Unknown required parameter 'unknown_param' for plugin MockPlugin",
        ):
            manager._get_constructor_params(MockPlugin, config)

    def test_convention_based_parameter_names(self) -> None:
        """Test that the simple convention works - 'config' and 'global_config'."""

        # Create a mock plugin class that uses the convention
        class MockPluginWithConvention:
            def __init__(self, config, global_config=None):
                pass

        manager = PluginManager()
        config = FrontmatterPluginConfig()

        # Should work without global_config since it has default value
        params = manager._get_constructor_params(MockPluginWithConvention, config)
        assert params == {"config": config}

        # Should include global_config when provided
        mock_global_config = Mock()
        manager = PluginManager(global_config=mock_global_config)
        params = manager._get_constructor_params(MockPluginWithConvention, config)
        assert params == {"config": config, "global_config": mock_global_config}
