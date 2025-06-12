"""Tests for path resolution functionality."""

from pathlib import Path

from scribe.config import ScribeConfig
from scribe.note_plugins.config import (
    ImageEncodingPluginConfig,
    SnapshotPluginConfig,
)
from scribe.paths import resolve_path, resolve_paths_recursively


class TestPathResolution:
    """Test cases for path resolution utilities."""

    def test_resolve_path_absolute(self):
        """Test that absolute paths remain unchanged."""
        abs_path = Path("/absolute/path")
        base_dir = Path("/some/base/dir")

        result = resolve_path(abs_path, base_dir)
        assert result == abs_path

    def test_resolve_path_relative_with_base_dir(self, tmp_path):
        """Test that relative paths are resolved relative to base dir."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        relative_path = Path("relative/path")
        result = resolve_path(relative_path, base_dir)

        expected = base_dir / "relative/path"
        assert result == expected

    def test_resolve_path_relative_no_base_dir(self):
        """Test that relative paths remain unchanged when no base dir provided."""
        relative_path = Path("relative/path")
        result = resolve_path(relative_path, None)

        assert result == relative_path

    def test_resolve_path_tilde_expansion(self):
        """Test that tilde paths are expanded."""
        tilde_path = "~/documents"
        result = resolve_path(tilde_path, None)

        expected = Path.home() / "documents"
        assert result == expected


class TestConfigPathResolution:
    """Test cases for config-level path resolution."""

    def test_plugin_config_path_resolution_dict(self, tmp_path):
        """Test path resolution for dict-based plugin configs."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        config_file = project_dir / "scribe.yml"
        config_file.write_text("""
site_title: "Test Project"
source_dir: "content"
output_dir: "dist"
note_plugins:
  - name: "snapshot"
    enabled: true
    snapshot_dir: "./snapshots"
  - name: "image_encoding"
    enabled: true
    cache_dir: ".image_cache"
""")

        config = ScribeConfig(config_file=config_file)

        # Check main paths
        assert config.source_dir == project_dir / "content"
        assert config.output_dir == project_dir / "dist"

        # Check plugin paths are resolved
        for plugin in config.note_plugins:
            if isinstance(plugin, dict):
                if plugin.get("name") == "snapshot":
                    expected_path = str(project_dir / "snapshots")
                    assert plugin.get("snapshot_dir") == expected_path
                elif plugin.get("name") == "image_encoding":
                    expected_path = str(project_dir / ".image_cache")
                    assert plugin.get("cache_dir") == expected_path

    def test_plugin_config_path_resolution_typed(self, tmp_path):
        """Test path resolution for typed plugin configs."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create configs directly
        snapshot_config = SnapshotPluginConfig(snapshot_dir=Path("./snapshots"))

        image_config = ImageEncodingPluginConfig(cache_dir=Path(".image_cache"))

        # Test resolve_paths_recursively directly on the plugin configs
        resolve_paths_recursively(snapshot_config, project_dir)
        resolve_paths_recursively(image_config, project_dir)

        # Check plugin paths are resolved
        assert snapshot_config.snapshot_dir == project_dir / "snapshots"
        assert image_config.cache_dir == project_dir / ".image_cache"

    def test_no_base_dir_no_resolution(self):
        """Test that without base dir, no path resolution occurs."""
        snapshot_config = SnapshotPluginConfig(snapshot_dir=Path("./snapshots"))

        # Don't call resolve_paths_recursively
        # Path should remain as-is since no resolution was performed
        assert snapshot_config.snapshot_dir == Path("./snapshots")

    def test_resolve_paths_recursively_on_dict(self, tmp_path):
        """Test resolve_paths_recursively on dictionary structures."""
        base_dir = tmp_path / "project"
        base_dir.mkdir()

        data = {
            "name": "test",
            "snapshot_dir": "./snapshots",
            "cache_dir": Path(".cache"),
            "nested": {"some_path": "relative/path", "absolute_path": "/absolute/path"},
        }

        resolve_paths_recursively(data, base_dir)

        # Check that relative paths were resolved
        assert data["snapshot_dir"] == str(base_dir / "snapshots")
        assert data["cache_dir"] == str(base_dir / ".cache")
        assert data["nested"]["some_path"] == str(base_dir / "relative/path")
        # Absolute paths should remain unchanged
        assert data["nested"]["absolute_path"] == "/absolute/path"

    def test_resolve_paths_recursively_on_pydantic_model(self, tmp_path):
        """Test resolve_paths_recursively on Pydantic models."""
        base_dir = tmp_path / "project"
        base_dir.mkdir()

        config = SnapshotPluginConfig(snapshot_dir=Path("./snapshots"))
        resolve_paths_recursively(config, base_dir)

        assert config.snapshot_dir == base_dir / "snapshots"

    def test_template_path_resolution(self, tmp_path):
        """Test that template paths are also resolved correctly."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        config_file = project_dir / "config.yml"
        config_file.write_text("""
site_title: "Template Test"
templates:
  template_path: "my_templates"
  base_templates: ["index.html"]
  note_templates: []
""")

        config = ScribeConfig(config_file=config_file)

        assert config.templates.template_path == project_dir / "my_templates"

    def test_static_path_resolution(self, tmp_path):
        """Test that static_path is resolved correctly."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        config_file = project_dir / "config.yml"
        config_file.write_text("""
site_title: "Static Test"
static_path: "assets"
""")

        config = ScribeConfig(config_file=config_file)

        assert config.static_path == project_dir / "assets"
