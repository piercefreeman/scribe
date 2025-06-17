"""Configuration management for Scribe."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .build_plugins.config import BuildPluginConfig
from .note_plugins.config import PluginConfig
from .paths import resolve_paths_recursively


class NoteTemplate(BaseModel):
    """Configuration for a note template with predicates."""

    template_path: str = Field(
        description="Path to the template file relative to template_path"
    )
    url_pattern: str = Field(
        description="URL pattern for matching notes (e.g., '/notes/{slug}/')"
    )
    predicates: list[str] = Field(
        default_factory=list,
        description="List of predicate functions to filter which notes match "
        "this template",
    )


class TemplateConfig(BaseModel):
    """Configuration for template system."""

    template_path: Path = Field(
        description="Base directory containing all template files"
    )
    base_templates: list[str] = Field(
        default_factory=list,
        description="List of template files to compile 1:1 to HTML "
        "(relative to template_path)",
    )
    note_templates: list[NoteTemplate] = Field(
        default_factory=list,
        description="List of note template configurations with predicates",
    )


class ScribeConfig(BaseSettings):
    """Main configuration for Scribe static site generator."""

    model_config = SettingsConfigDict(
        env_prefix="SCRIBE_",
        yaml_file=Path.home() / ".scribe" / "config.yml",
        yaml_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Environment setting
    environment: Literal["development", "production"] = Field(
        default="development",
        description="Environment mode - affects behavior of certain plugins "
        "(controlled by SCRIBE_ENVIRONMENT env var)",
    )

    # Source and output directories
    source_dir: Path = Field(
        default=Path.cwd() / "content",
        description="Directory containing source markdown files",
    )
    output_dir: Path = Field(
        default=Path.cwd() / "dist",
        description="Directory where generated site will be written",
    )

    # Development server settings
    host: str = Field(default="127.0.0.1", description="Development server host")
    port: int = Field(default=8000, description="Development server port")

    # Site metadata
    site_title: str = Field(default="My Site", description="Site title")
    site_description: str = Field(default="", description="Site description")
    site_url: str = Field(default="", description="Base URL for the site")

    # Plugin configuration
    note_plugins: list[PluginConfig] = Field(
        default_factory=list,
        description="List of enabled note plugins and their configurations",
    )

    # Build plugin configuration
    build_plugins: list[BuildPluginConfig] = Field(
        default_factory=list,
        description="List of enabled build plugins and their configurations",
    )

    # Template settings
    template_dir: Path | None = Field(
        default=None,
        description="Directory containing custom templates "
        "(deprecated, use templates instead)",
    )
    templates: TemplateConfig | None = Field(
        default=None, description="Template configuration for Jinja2 templates"
    )
    static_path: Path | None = Field(
        default=None,
        description="Directory containing static files to copy directly to output",
    )

    # Build settings
    clean_output: bool = Field(
        default=True, description="Clean output directory before building"
    )

    def __init__(self, config_file: Path | None = None, **kwargs: Any) -> None:
        # If custom config file is provided, load from it using PyYAML directly
        if config_file is not None and config_file.exists():
            import yaml

            try:
                with open(config_file, encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
                # Merge loaded config with kwargs, giving priority to kwargs
                kwargs = {**config_data, **kwargs}
            except Exception:
                # If loading fails, continue with defaults
                pass

        super().__init__(**kwargs)

        # Store the custom config file path after super().__init__
        self._custom_config_file = config_file

        # Resolve paths relative to config file directory if using custom config
        config_dir = None
        if config_file is not None:
            config_dir = config_file.parent

        # Resolve all paths in the entire config object (including plugins)
        if config_dir is not None:
            resolve_paths_recursively(self, config_dir)

    @property
    def config_dir(self) -> Path:
        """Return the .scribe configuration directory."""
        return Path.home() / ".scribe"

    @property
    def config_file_path(self) -> Path:
        """Return the path to the configuration file."""
        if self._custom_config_file is not None:
            return self._custom_config_file
        return self.config_dir / "config.yml"

    def config_file_exists(self) -> bool:
        """Check if the configuration file exists."""
        return self.config_file_path.exists()

    def ensure_config_dir(self) -> None:
        """Ensure the configuration directory exists."""
        self.config_dir.mkdir(exist_ok=True)

    def save_config(self) -> None:
        """Save current configuration to YAML file."""
        self.ensure_config_dir()
        config_path = self.config_dir / "config.yml"

        # Convert to dict for serialization
        config_dict = self.model_dump(mode="json")

        with open(config_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2)
