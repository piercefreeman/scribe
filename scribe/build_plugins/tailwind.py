"""Tailwind CSS build plugin for Scribe."""

import asyncio
from pathlib import Path

from scribe.build_plugins.base import BuildPlugin
from scribe.build_plugins.config import BuildPluginName, TailwindBuildPluginConfig
from scribe.config import ScribeConfig
from scribe.logger import get_logger

logger = get_logger(__name__)


class TailwindBuildPlugin(BuildPlugin[TailwindBuildPluginConfig]):
    """Build plugin that executes Tailwind CSS compilation."""

    name = BuildPluginName.TAILWIND

    async def after_all(self, site_config: ScribeConfig, output_dir: Path) -> None:
        """Execute Tailwind CSS compilation."""
        # Get input path from config
        input_css = self.config.input

        # Resolve input path relative to site config base path
        # (where the config file is located)
        config_base_path = site_config.config_file_path.parent
        input_path = config_base_path / input_css

        # Output directly to the build output directory with default filename
        output_path = output_dir / "styles.css"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build Tailwind command using the new CLI
        cmd = ["npx", "@tailwindcss/cli", "-i", str(input_path), "-o", str(output_path)]

        # Add watch flag if in config
        if self.config.watch:
            cmd.append("--watch")

        # Add minify flag if in config
        if self.config.minify:
            cmd.append("--minify")

        # Add additional flags from config
        extra_flags = self.config.flags
        if extra_flags:
            cmd.extend(extra_flags)

        try:
            # Execute Tailwind command from the config base directory
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=config_base_path,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"Tailwind compilation failed: {error_msg}")

            logger.info(
                f"Tailwind CSS compiled successfully: {output_path} "
                f"{stdout.decode()} {stderr.decode()}"
            )

        except FileNotFoundError:
            raise RuntimeError(
                "Tailwind CSS CLI not found. Please install it with: "
                "npm install -D @tailwindcss/cli"
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
