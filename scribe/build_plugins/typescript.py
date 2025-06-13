"""TypeScript build plugin for Scribe."""

import asyncio
from pathlib import Path

from scribe.build_plugins.base import BuildPlugin
from scribe.build_plugins.config import (
    BuildPluginName,
    TypeScriptBuildPluginConfig,
)
from scribe.config import ScribeConfig
from scribe.logger import get_logger

logger = get_logger(__name__)


class TypeScriptBuildPlugin(BuildPlugin[TypeScriptBuildPluginConfig]):
    """Build plugin that executes TypeScript compilation."""

    name = BuildPluginName.TYPESCRIPT

    async def after_all(self, site_config: ScribeConfig, output_dir: Path) -> None:
        """Execute TypeScript compilation."""
        # Get source directory from config
        source_dir = self.config.source

        # Resolve source path relative to site config base path
        # (where the config file is located)
        config_base_path = site_config.config_file_path.parent
        source_path = config_base_path / source_dir

        # Get output directory from config, default to js/ in build output
        output_subdir = self.config.output
        output_path = output_dir / output_subdir

        # Ensure source directory exists
        if not source_path.exists():
            raise RuntimeError(f"TypeScript source directory not found: {source_path}")

        # Ensure output directory exists
        output_path.mkdir(parents=True, exist_ok=True)

        # Build TypeScript command
        cmd = ["npx", "tsc"]

        # Add source files/directory
        if source_path.is_dir():
            # If it's a directory, add all .ts files recursively
            ts_files = list(source_path.rglob("*.ts"))
            if not ts_files:
                logger.warning(f"No TypeScript files found in {source_path}")
                return
            cmd.extend([str(f) for f in ts_files])
        else:
            # If it's a specific file
            cmd.append(str(source_path))

        # Add output directory
        cmd.extend(["--outDir", str(output_path)])

        # Add target option
        target = self.config.target
        cmd.extend(["--target", target])

        # Add module option
        module = self.config.module
        cmd.extend(["--module", module])

        # Add moduleResolution option
        if self.config.moduleResolution:
            cmd.extend(["--moduleResolution", self.config.moduleResolution])

        # Add strict mode if enabled
        if self.config.strict:
            cmd.append("--strict")

        # Add source maps if enabled
        if self.config.sourceMap:
            cmd.append("--sourceMap")

        # Add declaration files if enabled
        if self.config.declaration:
            cmd.append("--declaration")

        # Add watch flag if in config
        if self.config.watch:
            cmd.append("--watch")

        # Add additional flags from config
        extra_flags = self.config.flags
        if extra_flags:
            cmd.extend(extra_flags)

        try:
            # Execute TypeScript command from the config base directory
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=config_base_path,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(
                    f"TypeScript compilation failed: {stderr.decode()} "
                    f"{stdout.decode()}"
                )

            logger.info(f"TypeScript compiled successfully to: {output_path}")

            # Log any warnings or info from stdout/stderr
            if stdout:
                logger.debug(f"TypeScript stdout: {stdout.decode()}")
            if stderr:
                logger.debug(f"TypeScript stderr: {stderr.decode()}")

        except FileNotFoundError:
            raise RuntimeError(
                "TypeScript compiler not found. Please install it with: "
                "npm install -g typescript"
            ) from None

    # Legacy method - remove when all plugins are updated
    async def execute(self, site_config: ScribeConfig, output_dir: Path) -> None:
        await self.after_all(site_config, output_dir)

    def setup(self) -> None:
        """Setup hook called when plugin is loaded."""
        pass

    def teardown(self) -> None:
        """Teardown hook called when plugin is unloaded."""
        pass
