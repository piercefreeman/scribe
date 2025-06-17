"""Tests for ScribeConfig class."""

import os
from pathlib import Path
from unittest.mock import patch

from scribe.config import ScribeConfig


class TestScribeConfig:
    """Test cases for ScribeConfig."""

    def test_default_config_initialization(self):
        """Test that ScribeConfig initializes with default values."""
        config = ScribeConfig()

        assert config.source_dir == Path.cwd() / "content"
        assert config.output_dir == Path.cwd() / "dist"
        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.site_title == "My Site"
        assert config.site_description == ""
        assert config.clean_output is True
        assert config._custom_config_file is None

    def test_config_file_path_default(self):
        """Test that config_file_path returns default path when no custom file
        is specified."""
        config = ScribeConfig()
        expected_path = Path.home() / ".scribe" / "config.yml"
        assert config.config_file_path == expected_path

    def test_config_file_path_custom(self, tmp_path):
        """Test that config_file_path returns custom path when specified."""
        custom_path = tmp_path / "custom_config.yml"
        custom_path.touch()  # Create the file
        config = ScribeConfig(config_file=custom_path)
        assert config.config_file_path == custom_path

    def test_environment_from_env_var(self):
        """Test that SCRIBE_ENVIRONMENT environment variable sets the environment."""
        # Test production environment
        with patch.dict(os.environ, {"SCRIBE_ENVIRONMENT": "production"}):
            config = ScribeConfig()
            assert config.environment == "production"

        # Test development environment
        with patch.dict(os.environ, {"SCRIBE_ENVIRONMENT": "development"}):
            config = ScribeConfig()
            assert config.environment == "development"

    def test_environment_kwargs_override_env_var(self):
        """Test that explicit kwargs override environment variables."""
        with patch.dict(os.environ, {"SCRIBE_ENVIRONMENT": "production"}):
            config = ScribeConfig(environment="development")
            assert config.environment == "development"

    def test_environment_config_file_and_env_var(self, tmp_path):
        """Test environment precedence: env var > config file > default."""
        config_file = tmp_path / "test_config.yml"
        config_file.write_text("""
environment: "development"
site_title: "Test Site"
""")

        # Test that env var overrides config file
        with patch.dict(os.environ, {"SCRIBE_ENVIRONMENT": "production"}):
            config = ScribeConfig(config_file=config_file)
            assert config.environment == "production"

        # Test that kwargs override both env var and config file
        with patch.dict(os.environ, {"SCRIBE_ENVIRONMENT": "production"}):
            config = ScribeConfig(config_file=config_file, environment="development")
            assert config.environment == "development"

    def test_custom_config_file_loading(self, tmp_path):
        """Test loading configuration from a custom YAML file."""
        config_file = tmp_path / "test_config.yml"
        config_file.write_text("""
site_title: "Test Site"
site_description: "Test Description"
source_dir: "custom/source"
output_dir: "custom/output"
host: "0.0.0.0"
port: 9000
clean_output: false
""")

        config = ScribeConfig(config_file=config_file)

        assert config.site_title == "Test Site"
        assert config.site_description == "Test Description"
        # Relative paths should be resolved relative to config file directory
        assert config.source_dir == tmp_path / "custom/source"
        assert config.output_dir == tmp_path / "custom/output"
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.clean_output is False
        assert config._custom_config_file == config_file

    def test_custom_config_file_nonexistent(self, tmp_path):
        """Test behavior when custom config file doesn't exist."""
        nonexistent_path = tmp_path / "nonexistent.yml"
        config = ScribeConfig(config_file=nonexistent_path)

        # Should fall back to defaults since file doesn't exist
        assert config.site_title == "My Site"
        assert config.source_dir == Path.cwd() / "content"
        assert config._custom_config_file == nonexistent_path

    def test_config_file_exists_default(self):
        """Test config_file_exists with default config path."""
        config = ScribeConfig()

        # Mock the exists method to test both cases
        with patch.object(Path, "exists", return_value=True):
            assert config.config_file_exists() is True

        with patch.object(Path, "exists", return_value=False):
            assert config.config_file_exists() is False

    def test_config_file_exists_custom(self, tmp_path):
        """Test config_file_exists with custom config path."""
        config_file = tmp_path / "test_config.yml"
        config_file.touch()  # Create the file

        config = ScribeConfig(config_file=config_file)

        # File exists
        assert config.config_file_exists() is True

        # Remove file and test again
        config_file.unlink()
        assert config.config_file_exists() is False

    def test_kwargs_override_config_file(self, tmp_path):
        """Test that kwargs override values from config file."""
        config_file = tmp_path / "test_config.yml"
        config_file.write_text("""
site_title: "File Title"
port: 8000
""")

        config = ScribeConfig(
            config_file=config_file, site_title="Override Title", port=9999
        )

        # kwargs should override file values
        assert config.site_title == "Override Title"
        assert config.port == 9999

    def test_invalid_yaml_file(self, tmp_path):
        """Test behavior with invalid YAML file."""
        config_file = tmp_path / "invalid_config.yml"
        config_file.write_text("invalid: yaml: content: [")

        config = ScribeConfig(config_file=config_file)

        # Should fall back to defaults when YAML is invalid
        assert config.site_title == "My Site"
        assert config._custom_config_file == config_file

    def test_path_conversion(self, tmp_path):
        """Test that string paths are converted to Path objects."""
        config_file = tmp_path / "test_config.yml"
        config_file.write_text("""
source_dir: "string/source"
output_dir: "string/output"
""")

        config = ScribeConfig(config_file=config_file)

        assert isinstance(config.source_dir, Path)
        assert isinstance(config.output_dir, Path)
        # Relative paths should be resolved relative to config file directory
        assert config.source_dir == tmp_path / "string/source"
        assert config.output_dir == tmp_path / "string/output"

    def test_config_loading_with_relative_paths(self, tmp_path):
        """Test loading config with relative paths that get resolved properly."""
        config_file = tmp_path / "test_config.yml"
        config_file.write_text("""
site_title: "Relative Path Test"
source_dir: "content"
output_dir: "dist"
static_path: "static"
""")

        config = ScribeConfig(config_file=config_file)

        # Paths should be converted to Path objects
        assert isinstance(config.source_dir, Path)
        assert isinstance(config.output_dir, Path)
        assert isinstance(config.static_path, Path)
        assert config.site_title == "Relative Path Test"

    def test_relative_paths_resolved_relative_to_config_file(self, tmp_path):
        """Test that relative paths in config are resolved relative to config
        file directory."""
        # Create a nested directory structure
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config_file = config_dir / "site_config.yml"

        # Create some directories relative to the config file
        (config_dir / "my_content").mkdir()
        (config_dir / "my_output").mkdir()
        (config_dir / "my_static").mkdir()

        config_file.write_text("""
site_title: "Relative Path Test"
source_dir: "my_content"
output_dir: "my_output"
static_path: "my_static"
""")

        config = ScribeConfig(config_file=config_file)

        # Paths should be resolved relative to config file directory
        assert config.source_dir == config_dir / "my_content"
        assert config.output_dir == config_dir / "my_output"
        assert config.static_path == config_dir / "my_static"
        assert config.site_title == "Relative Path Test"

    def test_absolute_paths_remain_unchanged(self, tmp_path):
        """Test that absolute paths in config remain unchanged."""
        config_file = tmp_path / "test_config.yml"

        abs_source = tmp_path / "absolute_source"
        abs_output = tmp_path / "absolute_output"
        abs_static = tmp_path / "absolute_static"

        config_file.write_text(f"""
site_title: "Absolute Path Test"
source_dir: "{abs_source}"
output_dir: "{abs_output}"
static_path: "{abs_static}"
""")

        config = ScribeConfig(config_file=config_file)

        # Absolute paths should remain unchanged
        assert config.source_dir == abs_source
        assert config.output_dir == abs_output
        assert config.static_path == abs_static

    def test_mixed_relative_and_absolute_paths(self, tmp_path):
        """Test config with mix of relative and absolute paths."""
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config_file = config_dir / "mixed_config.yml"

        # Create relative directory
        (config_dir / "rel_content").mkdir()

        # Absolute paths
        abs_output = tmp_path / "abs_output"
        abs_static = tmp_path / "abs_static"

        config_file.write_text(f"""
site_title: "Mixed Path Test"
source_dir: "rel_content"
output_dir: "{abs_output}"
static_path: "{abs_static}"
""")

        config = ScribeConfig(config_file=config_file)

        # Relative path should be resolved relative to config file
        assert config.source_dir == config_dir / "rel_content"
        # Absolute paths should remain unchanged
        assert config.output_dir == abs_output
        assert config.static_path == abs_static

    def test_templates_path_resolution(self, tmp_path):
        """Test that template paths are also resolved relative to config file."""
        config_dir = tmp_path / "project"
        config_dir.mkdir()
        config_file = config_dir / "config.yml"

        # Create template directory relative to config
        (config_dir / "my_templates").mkdir()

        config_file.write_text("""
site_title: "Template Path Test"
templates:
  template_path: "my_templates"
  base_templates: ["base.html"]
  note_templates: []
""")

        config = ScribeConfig(config_file=config_file)

        # Template path should be resolved relative to config file
        assert config.templates.template_path == config_dir / "my_templates"

    def test_default_config_paths_unchanged(self):
        """Test that default config (no custom file) keeps current directory
        behavior."""
        config = ScribeConfig()

        # Default paths should remain relative to current directory
        assert config.source_dir == Path.cwd() / "content"
        assert config.output_dir == Path.cwd() / "dist"

    def test_end_to_end_relative_path_resolution(self, tmp_path):
        """End-to-end test demonstrating relative path resolution."""
        # Create a project structure
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        # Create subdirectories
        (project_dir / "content").mkdir()
        (project_dir / "build").mkdir()
        (project_dir / "assets").mkdir()
        (project_dir / "themes").mkdir()

        # Create config file in project directory
        config_file = project_dir / "scribe.yml"
        config_file.write_text("""
site_title: "My Project"
site_description: "A test project"
source_dir: "content"
output_dir: "build"
static_path: "assets"
templates:
  template_path: "themes"
  base_templates: ["index.html"]
""")

        # Load config
        config = ScribeConfig(config_file=config_file)

        # All paths should be resolved relative to the config file location
        assert config.site_title == "My Project"
        assert config.source_dir == project_dir / "content"
        assert config.output_dir == project_dir / "build"
        assert config.static_path == project_dir / "assets"
        assert config.templates.template_path == project_dir / "themes"

        # Config file path should be correct
        assert config.config_file_path == config_file
        assert config.config_file_exists() is True

    def test_tilde_path_expansion(self, tmp_path):
        """Test that paths with ~ are expanded to user home directory."""
        config_file = tmp_path / "test_config.yml"
        config_file.write_text("""
site_title: "Tilde Path Test"
source_dir: "~/notes"
output_dir: "~/output"
static_path: "~/static"
""")

        config = ScribeConfig(config_file=config_file)

        # Paths with ~ should be expanded to user home directory
        assert config.source_dir == Path.home() / "notes"
        assert config.output_dir == Path.home() / "output"
        assert config.static_path == Path.home() / "static"

    def test_tilde_path_expansion_in_templates(self, tmp_path):
        """Test that template paths with ~ are expanded to user home directory."""
        config_file = tmp_path / "test_config.yml"
        config_file.write_text("""
site_title: "Template Tilde Test"
templates:
  template_path: "~/templates"
  base_templates: ["base.html"]
  note_templates: []
""")

        config = ScribeConfig(config_file=config_file)

        # Template path with ~ should be expanded to user home directory
        assert config.templates.template_path == Path.home() / "templates"
