"""Build plugin configuration models."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from scribe.plugins import BasePluginConfig, PluginNameEnum


class BuildPluginName(PluginNameEnum):
    """Enum for build plugin names."""

    TAILWIND = "tailwind"
    TYPESCRIPT = "typescript"


class BaseBuildPluginConfig(BasePluginConfig[BuildPluginName]):
    """Base configuration for all build plugins."""

    pass


class TailwindBuildPluginConfig(BaseBuildPluginConfig):
    """Configuration for the Tailwind CSS build plugin.

    The output CSS file will be automatically placed in the appropriate build output
    directory (dev or production) as "styles.css".

    Example YAML configuration:
    ```yaml
    tailwind:
      name: tailwind
      enabled: true
      input: "src/input.css"
      watch: false
      minify: true
      flags: []
      verbose: false
    ```
    """

    name: Literal[BuildPluginName.TAILWIND] = BuildPluginName.TAILWIND
    input: Path
    watch: bool = False
    minify: bool = True
    flags: list[str] = Field(default_factory=list)
    verbose: bool = False


class TypeScriptBuildPluginConfig(BaseBuildPluginConfig):
    """Configuration for the TypeScript build plugin.

    Compiles TypeScript files from a source directory and outputs them to the build
    directory. The compiled JavaScript files can then be imported in frontend code.

    Example YAML configuration:
    ```yaml
    typescript:
      name: typescript
      enabled: true
      source: "src/ts"
      output: "js"
      target: "es2020"
      module: "es6"
      moduleResolution: "nodenext"
      strict: true
      sourceMap: true
      declaration: false
      watch: false
      flags: []
    ```
    """

    name: Literal[BuildPluginName.TYPESCRIPT] = BuildPluginName.TYPESCRIPT
    source: Path
    output: str = "scripts"
    target: str = "es2020"
    module: str = "es2020"
    moduleResolution: str = "classic"
    strict: bool = True
    sourceMap: bool = True
    declaration: bool = False
    watch: bool = False
    flags: list[str] = Field(default_factory=list)


BuildPluginConfig = Annotated[
    TailwindBuildPluginConfig | TypeScriptBuildPluginConfig,
    Field(discriminator="name"),
]
