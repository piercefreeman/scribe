"""Image encoding plugin for processing images referenced in page content."""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

if TYPE_CHECKING:
    from scribe.config import ScribeConfig

from scribe.context import ImageEncodingData, PageContext
from scribe.logger import get_logger
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import ImageEncodingPluginConfig, PluginName

logger = get_logger(__name__)


class ImageEncodingPlugin(NotePlugin[ImageEncodingPluginConfig]):
    """Plugin that processes and optimizes images referenced in page content."""

    name = PluginName.IMAGE_ENCODING

    def __init__(
        self,
        config: ImageEncodingPluginConfig,
        global_config: "ScribeConfig",
    ) -> None:
        super().__init__(config)
        self.global_config = global_config
        self._check_format_support()

    def _check_format_support(self) -> None:
        """Check which formats are supported."""
        self.supports_avif = self._test_format_support("AVIF", ".avif")
        self.supports_webp = self._test_format_support("WEBP", ".webp")

    def _test_format_support(self, pil_format: str, extension: str) -> bool:
        """Test if PIL supports a specific format."""
        try:
            test_img = Image.new("RGB", (1, 1))
            with tempfile.NamedTemporaryFile(
                suffix=extension, delete=False
            ) as tmp_file:
                test_img.save(tmp_file.name, format=pil_format)
                os.unlink(tmp_file.name)
            return True
        except Exception:
            return False

    async def process(self, ctx: PageContext) -> PageContext:
        """Process images referenced in the page content."""

        # Find image references in the content
        image_refs = self._extract_image_references(ctx.content)

        # Also add featured_photos from the context
        if ctx.featured_photos:
            image_refs.extend(ctx.featured_photos)
            # Remove duplicates while preserving order
            image_refs = list(dict.fromkeys(image_refs))

        if not image_refs:
            return ctx

        # Set up cache directory
        cache_dir = self.config.cache_dir
        if not cache_dir.is_absolute():
            cache_dir = Path.cwd() / cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Process each image
        processed_images = {}
        for img_src in image_refs:
            try:
                processed_formats = await self._process_image(img_src, cache_dir, ctx)
                if processed_formats:
                    processed_images[img_src] = processed_formats
            except Exception as e:
                logger.error(f"Error processing {img_src}: {e}")

        # Store processed image info as typed attribute
        ctx.image_encoding_data = ImageEncodingData(
            processed_images=processed_images,
            formats=self.config.formats,
        )

        # Rewrite image paths in content to use the converted formats
        if processed_images:
            ctx.content = self._rewrite_image_paths(ctx.content, processed_images, ctx)

            # Also update featured_photos to point to converted images
            if ctx.featured_photos:
                ctx.featured_photos = self._update_featured_photos(
                    ctx.featured_photos, processed_images, ctx
                )

        return ctx

    def _extract_image_references(self, content: str) -> list[str]:
        """Extract image references from markdown content."""
        image_refs = []

        # Markdown images: ![alt](src)
        for match in re.finditer(r"!\[.*?\]\(([^)]+)\)", content):
            src = match.group(1)
            if not src.startswith(("http://", "https://", "//")):
                image_refs.append(src)

        # HTML img tags: <img src="...">
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', content):
            src = match.group(1)
            if not src.startswith(("http://", "https://", "//")):
                image_refs.append(src)

        return list(set(image_refs))

    async def _process_image(
        self, img_src: str, cache_dir: Path, ctx: PageContext
    ) -> list[str]:
        """Process a single image and return list of generated formats."""
        # Find the source image
        source_path = self._find_image_path(img_src, ctx)
        if not source_path or not source_path.exists():
            logger.warning(f"Image not found: {img_src}")
            return []

        # Create simple cache key from relative path
        cache_key = self._get_cache_key(source_path, ctx)
        image_cache_dir = cache_dir / cache_key

        # If cache exists and is newer than source, just copy it over
        if self._is_cache_valid(image_cache_dir, source_path):
            await self._copy_cache_to_output(image_cache_dir, source_path, ctx)
            cached_files = list(image_cache_dir.glob("*"))
            logger.debug(
                f"Cached files for {img_src}: "
                f"{[f.name for f in cached_files if f.is_file()]}"
            )
            return [f.suffix[1:] for f in cached_files if f.is_file() and f.suffix]

        # Create fresh cache
        image_cache_dir.mkdir(parents=True, exist_ok=True)

        # Process the image
        processed_formats = []
        try:
            with Image.open(source_path) as img:
                # Convert and orient the image
                img = self._prepare_image(img)

                # Generate each requested format
                for format_name in self.config.formats:
                    if self._process_format(
                        img, format_name, source_path, image_cache_dir
                    ):
                        processed_formats.append(format_name)

            # Copy cache to output
            await self._copy_cache_to_output(image_cache_dir, source_path, ctx)

            # Debug: check what files were created
            cached_files = list(image_cache_dir.glob("*"))
            logger.debug(
                f"Generated cache files for {img_src}: "
                f"{[f.name for f in cached_files if f.is_file()]}"
            )

        except Exception as e:
            logger.error(f"Error processing image {source_path}: {e}")
            return []

        return processed_formats

    def _find_image_path(self, img_src: str, ctx: PageContext) -> Path | None:
        """Find the actual path to an image."""
        # Try relative to page directory
        page_dir = ctx.source_path.parent
        if (page_dir / img_src).exists():
            return page_dir / img_src

        # Try relative to source directory
        if (self.global_config.source_dir / img_src).exists():
            return self.global_config.source_dir / img_src

        # Try relative to static directory
        if (
            self.global_config.static_path
            and (self.global_config.static_path / img_src).exists()
        ):
            return self.global_config.static_path / img_src

        return None

    def _get_cache_key(self, source_path: Path, ctx: PageContext) -> str:
        """Generate a simple cache key based on the file path."""
        # Try to get relative path from source_dir or static_path
        try:
            rel_path = source_path.relative_to(self.global_config.source_dir)
        except ValueError:
            try:
                if self.global_config.static_path:
                    rel_path = source_path.relative_to(self.global_config.static_path)
                else:
                    rel_path = Path(source_path.name)
            except ValueError:
                rel_path = Path(source_path.name)

        # Convert path to safe directory name
        return str(rel_path).replace("/", "_").replace("\\", "_")

    def _is_cache_valid(self, cache_dir: Path, source_path: Path) -> bool:
        """Check if cache is valid (exists and newer than source)."""
        if not cache_dir.exists():
            return False

        source_mtime = source_path.stat().st_mtime

        # Check if any cached file is older than source
        for cached_file in cache_dir.glob("*"):
            if cached_file.is_file() and cached_file.stat().st_mtime <= source_mtime:
                return False

        return True

    def _prepare_image(self, img: Image.Image) -> Image.Image:
        """Prepare image for processing."""
        # Convert to RGB if necessary
        if img.mode in ("RGBA", "LA", "P"):
            if img.mode == "P" and "transparency" in img.info:
                img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # Apply auto-rotation
        return ImageOps.exif_transpose(img)

    def _process_format(
        self, img: Image.Image, format_name: str, source_path: Path, cache_dir: Path
    ) -> bool:
        """Process image in a specific format."""
        # Check format support
        if format_name == "avif" and not self.supports_avif:
            return False
        if format_name == "webp" and not self.supports_webp:
            return False
        if format_name not in ["avif", "webp"]:
            return False

        try:
            # Set format parameters
            if format_name == "avif":
                pil_format = "AVIF"
                quality = self.config.quality_avif
                extension = ".avif"
            else:  # webp
                pil_format = "WEBP"
                quality = self.config.quality_webp
                extension = ".webp"

            # Resize if needed
            processed_img = img
            if self.config.max_width and img.width > self.config.max_width:
                aspect_ratio = img.height / img.width
                new_height = int(self.config.max_width * aspect_ratio)
                processed_img = img.resize(
                    (self.config.max_width, new_height), Image.Resampling.LANCZOS
                )

            if self.config.max_height and processed_img.height > self.config.max_height:
                aspect_ratio = processed_img.width / processed_img.height
                new_width = int(self.config.max_height * aspect_ratio)
                processed_img = processed_img.resize(
                    (new_width, self.config.max_height), Image.Resampling.LANCZOS
                )

            # Save to cache
            output_file = cache_dir / f"{source_path.stem}{extension}"
            logger.debug(
                f"Saving {format_name} file: source_path.stem={source_path.stem}, "
                f"extension={extension}, output_file={output_file}"
            )
            processed_img.save(
                output_file, format=pil_format, quality=quality, optimize=True
            )

            return True

        except Exception as e:
            logger.error(f"Error saving {format_name} format: {e}")
            return False

    async def _copy_cache_to_output(
        self, cache_dir: Path, source_path: Path, ctx: PageContext
    ) -> None:
        """Copy the entire cache directory to output."""
        if not self.global_config or not cache_dir.exists():
            return

        try:
            # Determine output directory
            relative_path = self._get_output_path(source_path, ctx)
            output_dir = self.global_config.output_dir / relative_path.parent
            output_dir.mkdir(parents=True, exist_ok=True)

            # Copy all files from cache to output
            for cached_file in cache_dir.glob("*"):
                if cached_file.is_file():
                    output_file = output_dir / cached_file.name
                    logger.debug(
                        f"Copying cache file: {cached_file.name} -> {output_file}"
                    )
                    if (
                        not output_file.exists()
                        or cached_file.stat().st_mtime > output_file.stat().st_mtime
                    ):
                        shutil.copy2(cached_file, output_file)

        except Exception as e:
            logger.error(f"Error copying cache to output: {e}")

    def _get_output_path(self, source_path: Path, ctx: PageContext) -> Path:
        """Get the output path for a source image."""
        # Try to maintain directory structure
        try:
            return source_path.relative_to(self.global_config.source_dir)
        except ValueError:
            try:
                if self.global_config.static_path:
                    return source_path.relative_to(self.global_config.static_path)
            except ValueError:
                pass

        return Path(source_path.name)

    def _get_converted_image_path(
        self, img_src: str, formats: list[str], ctx: PageContext
    ) -> str:
        """Get the converted image path for a given source image."""
        if not formats:
            return img_src

        preferred_format = formats[0]

        # Get the base name without extension
        src_path = Path(img_src)
        base_name = src_path.stem

        # Find the source path to determine output location
        source_path = self._find_image_path(img_src, ctx)
        if source_path:
            # Get the output path relative to the output directory
            output_relative_path = self._get_output_path(source_path, ctx)
            output_dir = output_relative_path.parent

            # Construct absolute URL path from site root
            if output_dir != Path(".") and str(output_dir) != ".":
                new_src = f"/{output_dir}/{base_name}.{preferred_format}"
            else:
                new_src = f"/{base_name}.{preferred_format}"
        else:
            # Fallback: just use the base name with absolute path
            new_src = f"/{base_name}.{preferred_format}"

        # Normalize path separators for URLs
        return new_src.replace("\\", "/")

    def _update_featured_photos(
        self,
        featured_photos: list[str],
        processed_images: dict[str, list[str]],
        ctx: PageContext,
    ) -> list[str]:
        """Update featured_photos to point to converted images."""
        updated_photos = []
        for photo in featured_photos:
            if photo in processed_images and processed_images[photo]:
                new_src = self._get_converted_image_path(
                    photo, processed_images[photo], ctx
                )
                updated_photos.append(new_src)
                logger.debug(f"Updated featured photo: {photo} -> {new_src}")
            else:
                # Keep original if not processed
                updated_photos.append(photo)
        return updated_photos

    def _rewrite_image_paths(
        self, content: str, processed_images: dict[str, list[str]], ctx: PageContext
    ) -> str:
        """Rewrite image paths in content to use the converted formats."""
        for img_src, formats in processed_images.items():
            if not formats:
                continue

            new_src = self._get_converted_image_path(img_src, formats, ctx)

            logger.debug(f"Processing {img_src}: formats={formats}, new_src={new_src}")

            # Replace in markdown images: ![alt](src)
            content = re.sub(
                rf"!\[([^\]]*)\]\({re.escape(img_src)}\)", rf"![\1]({new_src})", content
            )

            # Replace in HTML img tags: <img src="...">
            content = re.sub(
                rf'(<img[^>]+src=["\']){re.escape(img_src)}(["\'][^>]*>)',
                rf"\1{new_src}\2",
                content,
            )

            logger.debug(f"Rewritten image path: {img_src} -> {new_src}")

        return content
