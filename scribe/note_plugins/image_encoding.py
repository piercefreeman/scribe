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
    """Plugin that processes and optimizes images with responsive sizing."""

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

        # Find image references in HTML content (since we run after markdown)
        image_refs = self._extract_html_image_references(ctx.content)

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
        responsive_images = {}
        image_dimensions = {}

        for img_src in image_refs:
            try:
                result = await self._process_image_responsive(img_src, cache_dir, ctx)
                if result:
                    formats, responsive_data, dimensions = result
                    processed_images[img_src] = formats
                    responsive_images[img_src] = responsive_data
                    image_dimensions[img_src] = dimensions
            except Exception as e:
                logger.error(f"Error processing {img_src}: {e}")

        # Store processed image info as typed attribute
        ctx.image_encoding_data = ImageEncodingData(
            processed_images=processed_images,
            formats=self.config.formats,
            responsive_images=responsive_images,
            image_dimensions=image_dimensions,
        )

        # Rewrite HTML image tags to use picture elements
        if processed_images:
            ctx.content = self._rewrite_html_to_picture_elements(
                ctx.content, responsive_images, image_dimensions, ctx
            )

            # Also update featured_photos to point to converted images
            if ctx.featured_photos:
                ctx.featured_photos = self._update_featured_photos(
                    ctx.featured_photos, responsive_images, ctx
                )

        return ctx

    def _extract_html_image_references(self, content: str) -> list[str]:
        """Extract image references from HTML content."""
        image_refs = []

        # HTML img tags: <img src="...">
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', content):
            src = match.group(1)
            if not src.startswith(("http://", "https://", "//")):
                image_refs.append(src)

        return list(set(image_refs))

    async def _process_image_responsive(
        self, img_src: str, cache_dir: Path, ctx: PageContext
    ) -> tuple[list[str], dict[str, dict[int, str]], tuple[int, int]] | None:
        """Process a single image and return responsive data."""
        # Find the source image
        source_path = self._find_image_path(img_src, ctx)
        if not source_path or not source_path.exists():
            logger.warning(f"Image not found: {img_src}")
            return None

        # Create cache key from relative path
        cache_key = self._get_cache_key(source_path, ctx)
        image_cache_dir = cache_dir / cache_key

        # Check if cache is valid
        if self._is_cache_valid(image_cache_dir, source_path):
            await self._copy_cache_to_output(image_cache_dir, source_path, ctx)
            return self._get_cached_responsive_data(image_cache_dir, source_path, ctx)

        # Create fresh cache
        image_cache_dir.mkdir(parents=True, exist_ok=True)

        # Process the image
        try:
            with Image.open(source_path) as img:
                # Convert and orient the image
                img = self._prepare_image(img)
                original_dimensions = img.size

                # Generate responsive sizes and formats
                processed_formats = []
                responsive_data = {}

                for format_name in self.config.formats:
                    if not self._format_supported(format_name):
                        continue

                    responsive_data[format_name] = {}
                    format_processed = False

                    if self.config.generate_responsive:
                        # Generate responsive sizes for this image
                        sizes_to_generate = []

                        # Add responsive sizes smaller than or equal to original
                        for size in self.config.responsive_sizes:
                            if size <= img.width:
                                sizes_to_generate.append(size)

                        # Always include original size if no responsive sizes fit
                        if not sizes_to_generate:
                            sizes_to_generate.append(img.width)
                        # Also add original size if it's not already included
                        elif img.width not in sizes_to_generate:
                            sizes_to_generate.append(img.width)

                        # Generate all applicable sizes
                        for size in sizes_to_generate:
                            if self._process_responsive_format(
                                img,
                                format_name,
                                size,
                                source_path,
                                image_cache_dir,
                                ctx,
                            ):
                                responsive_data[format_name][size] = (
                                    self._get_responsive_path(
                                        source_path, format_name, size, ctx
                                    )
                                )
                                format_processed = True
                    else:
                        # Generate single size (original dimensions)
                        if self._process_format(
                            img, format_name, source_path, image_cache_dir, ctx
                        ):
                            responsive_data[format_name][original_dimensions[0]] = (
                                self._get_converted_path(source_path, format_name, ctx)
                            )
                            format_processed = True

                    if format_processed:
                        processed_formats.append(format_name)

                # Copy cache to output
                await self._copy_cache_to_output(image_cache_dir, source_path, ctx)

                return processed_formats, responsive_data, original_dimensions

        except Exception as e:
            logger.error(f"Error processing image {source_path}: {e}")
            return None

    def _format_supported(self, format_name: str) -> bool:
        """Check if format is supported."""
        if format_name == "avif":
            return self.supports_avif
        elif format_name == "webp":
            return self.supports_webp
        return False

    def _process_responsive_format(
        self,
        img: Image.Image,
        format_name: str,
        target_width: int,
        source_path: Path,
        cache_dir: Path,
        ctx: PageContext,
    ) -> bool:
        """Process image in a specific format and size."""
        try:
            # Skip if target width is larger than original
            if target_width > img.width:
                return False

            # Set format parameters
            if format_name == "avif":
                pil_format = "AVIF"
                quality = self.config.quality_avif
                extension = ".avif"
            else:  # webp
                pil_format = "WEBP"
                quality = self.config.quality_webp
                extension = ".webp"

            # Resize image maintaining aspect ratio or use original
            if target_width == img.width:
                processed_img = img
            else:
                aspect_ratio = img.height / img.width
                new_height = int(target_width * aspect_ratio)
                processed_img = img.resize(
                    (target_width, new_height), Image.Resampling.LANCZOS
                )

            # Apply max_height constraint if specified
            if self.config.max_height and processed_img.height > self.config.max_height:
                aspect_ratio = processed_img.width / processed_img.height
                new_width = int(self.config.max_height * aspect_ratio)
                processed_img = processed_img.resize(
                    (new_width, self.config.max_height), Image.Resampling.LANCZOS
                )

            # Save to cache using slug-based naming
            base_name = ctx.generate_slug_from_text(source_path.stem)
            output_file = cache_dir / f"{base_name}-{target_width}{extension}"

            if self.config.verbose:
                logger.debug(f"Saving responsive {format_name} file: {output_file}")

            processed_img.save(
                output_file, format=pil_format, quality=quality, optimize=True
            )
            return True

        except Exception as e:
            logger.error(
                f"Error saving responsive {format_name} format at {target_width}w: {e}"
            )
            return False

    def _process_format(
        self,
        img: Image.Image,
        format_name: str,
        source_path: Path,
        cache_dir: Path,
        ctx: PageContext,
    ) -> bool:
        """Process image in a specific format (single size)."""
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

            # Save to cache using slug-based naming
            base_name = ctx.generate_slug_from_text(source_path.stem)
            output_file = cache_dir / f"{base_name}{extension}"

            processed_img.save(
                output_file, format=pil_format, quality=quality, optimize=True
            )
            return True

        except Exception as e:
            logger.error(f"Error saving {format_name} format: {e}")
            return False

    def _get_cached_responsive_data(
        self, cache_dir: Path, source_path: Path, ctx: PageContext
    ) -> tuple[list[str], dict[str, dict[int, str]], tuple[int, int]]:
        """Get responsive data from cached files."""
        processed_formats = []
        responsive_data = {}

        # Try to get original dimensions from a cached file
        original_dimensions = (1024, 768)  # fallback

        # Get directory structure for URL generation
        try:
            if self.global_config.static_path:
                output_relative_path = source_path.relative_to(
                    self.global_config.static_path
                )
            else:
                output_relative_path = source_path.relative_to(
                    self.global_config.source_dir
                )
        except ValueError:
            output_relative_path = Path(source_path.name)

        output_dir = output_relative_path.parent

        for format_name in self.config.formats:
            if not self._format_supported(format_name):
                continue

            extension = f".{format_name}"
            responsive_data[format_name] = {}

            # Find all cached files for this format
            for cached_file in cache_dir.glob(f"*{extension}"):
                # Extract width from filename (e.g., "image-480.webp" -> 480)
                name_part = cached_file.stem
                if "-" in name_part:
                    try:
                        width = int(name_part.split("-")[-1])
                        # Generate proper URL path with slug-based directory names
                        if output_dir != Path(".") and str(output_dir) != ".":
                            dir_parts = []
                            for part in output_dir.parts:
                                slug_part = ctx.generate_slug_from_text(part)
                                dir_parts.append(slug_part)
                            output_dir_str = "/".join(dir_parts)
                            path = f"/{output_dir_str}/{cached_file.name}"
                        else:
                            path = f"/{cached_file.name}"
                        responsive_data[format_name][width] = path.replace("\\", "/")
                    except ValueError:
                        # Fallback for non-responsive files
                        if output_dir != Path(".") and str(output_dir) != ".":
                            dir_parts = []
                            for part in output_dir.parts:
                                slug_part = ctx.generate_slug_from_text(part)
                                dir_parts.append(slug_part)
                            output_dir_str = "/".join(dir_parts)
                            path = f"/{output_dir_str}/{cached_file.name}"
                        else:
                            path = f"/{cached_file.name}"
                        responsive_data[format_name][1024] = path.replace("\\", "/")
                else:
                    # Non-responsive file
                    if output_dir != Path(".") and str(output_dir) != ".":
                        dir_parts = []
                        for part in output_dir.parts:
                            slug_part = ctx.generate_slug_from_text(part)
                            dir_parts.append(slug_part)
                        output_dir_str = "/".join(dir_parts)
                        path = f"/{output_dir_str}/{cached_file.name}"
                    else:
                        path = f"/{cached_file.name}"
                    responsive_data[format_name][1024] = path.replace("\\", "/")

            if responsive_data[format_name]:
                processed_formats.append(format_name)

        return processed_formats, responsive_data, original_dimensions

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
        """Generate a cache key based on the file path using proper slug formatting."""
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

        # Convert path to URL-safe directory name using slug logic
        path_str = str(rel_path.with_suffix(""))  # Remove extension

        # Convert each path component to a proper slug
        parts = []
        for part in path_str.split("/"):
            if part:  # Skip empty parts
                slug_part = ctx.generate_slug_from_text(part)
                parts.append(slug_part)

        # Join with underscores for directory safety
        return "_".join(parts) if parts else "image"

    def _is_cache_valid(self, cache_dir: Path, source_path: Path) -> bool:
        """Check if cache is valid (exists and newer than source)."""
        if not cache_dir.exists():
            return False

        source_mtime = source_path.stat().st_mtime

        # Check if any cached file is older than source
        for cached_file in cache_dir.glob("*"):
            if cached_file.is_file() and cached_file.stat().st_mtime <= source_mtime:
                return False

        return len(list(cache_dir.glob("*"))) > 0

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
                    if self.config.verbose:
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

    def _get_responsive_path(
        self, source_path: Path, format_name: str, width: int, ctx: PageContext
    ) -> str:
        """Get the responsive image path for a given source image, format, and width."""
        # Get the base name without extension and convert to proper slug
        base_name = ctx.generate_slug_from_text(source_path.stem)

        # Find the source path to determine output location
        output_relative_path = self._get_output_path(source_path, ctx)
        output_dir = output_relative_path.parent

        # Convert directory path components to proper slugs
        if output_dir != Path(".") and str(output_dir) != ".":
            dir_parts = []
            for part in output_dir.parts:
                slug_part = ctx.generate_slug_from_text(part)
                dir_parts.append(slug_part)
            output_dir_str = "/".join(dir_parts)
            path = f"/{output_dir_str}/{base_name}-{width}.{format_name}"
        else:
            path = f"/{base_name}-{width}.{format_name}"

        # Normalize path separators for URLs
        return path.replace("\\", "/")

    def _get_converted_path(
        self, source_path: Path, format_name: str, ctx: PageContext
    ) -> str:
        """Get the converted image path for a given source image and format."""
        # Get the base name without extension and convert to proper slug
        base_name = ctx.generate_slug_from_text(source_path.stem)

        # Find the source path to determine output location
        output_relative_path = self._get_output_path(source_path, ctx)
        output_dir = output_relative_path.parent

        # Convert directory path components to proper slugs
        if output_dir != Path(".") and str(output_dir) != ".":
            dir_parts = []
            for part in output_dir.parts:
                slug_part = ctx.generate_slug_from_text(part)
                dir_parts.append(slug_part)
            output_dir_str = "/".join(dir_parts)
            path = f"/{output_dir_str}/{base_name}.{format_name}"
        else:
            path = f"/{base_name}.{format_name}"

        # Normalize path separators for URLs
        return path.replace("\\", "/")

    def _rewrite_html_to_picture_elements(
        self,
        content: str,
        responsive_images: dict[str, dict[str, dict[int, str]]],
        image_dimensions: dict[str, tuple[int, int]],
        ctx: PageContext,
    ) -> str:
        """Rewrite HTML img tags to use picture elements with responsive images."""

        def replace_img_tag(match: re.Match) -> str:
            full_tag = match.group(0)
            img_src = match.group(1)

            # Skip if not in our processed images
            if img_src not in responsive_images:
                return full_tag

            # Extract attributes from original img tag
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', full_tag)
            alt_text = alt_match.group(1) if alt_match else ""

            class_match = re.search(r'class=["\']([^"\']*)["\']', full_tag)
            class_attr = f' class="{class_match.group(1)}"' if class_match else ""

            # Get image dimensions
            dimensions = image_dimensions.get(img_src, (1024, 768))
            width, height = dimensions

            if not self.config.use_picture_element:
                # Simple img tag with srcset
                return self._create_simple_responsive_img(
                    img_src,
                    responsive_images[img_src],
                    alt_text,
                    class_attr,
                    width,
                    height,
                )
            else:
                # Full picture element
                return self._create_picture_element(
                    img_src,
                    responsive_images[img_src],
                    alt_text,
                    class_attr,
                    width,
                    height,
                )

        # Replace all img tags
        pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        return re.sub(pattern, replace_img_tag, content)

    def _create_picture_element(
        self,
        img_src: str,
        formats_data: dict[str, dict[int, str]],
        alt_text: str,
        class_attr: str,
        width: int,
        height: int,
    ) -> str:
        """Create a picture element with source tags for each format."""
        sources = []
        fallback_src = ""

        # Create source elements for each format
        for format_name in self.config.formats:
            if format_name not in formats_data or not formats_data[format_name]:
                continue

            # Build srcset
            srcset_parts = []
            for size, path in sorted(formats_data[format_name].items()):
                srcset_parts.append(f"{path} {size}w")

            if srcset_parts:
                srcset = ", ".join(srcset_parts)
                mime_type = f"image/{format_name}"
                source_tag = (
                    f'  <source type="{mime_type}" '
                    f'srcset="{srcset}" '
                    f'sizes="{self.config.default_sizes}">'
                )
                sources.append(source_tag)

                # Use first format as fallback
                if not fallback_src:
                    # Use the largest size as fallback, or middle size if available
                    sizes = sorted(formats_data[format_name].keys())
                    fallback_size = (
                        sizes[-1] if len(sizes) == 1 else sizes[len(sizes) // 2]
                    )
                    fallback_src = formats_data[format_name][fallback_size]

        # Create fallback img tag
        loading_attr = (
            ' loading="lazy" decoding="async"' if self.config.add_loading_lazy else ""
        )
        img_attrs = (
            f'src="{fallback_src}" alt="{alt_text}"{class_attr}{loading_attr} '
            f'width="{width}" height="{height}"'
        )

        # Combine into picture element
        picture_parts = ["<picture>"] + sources + [f"  <img {img_attrs}>", "</picture>"]
        return "\n".join(picture_parts)

    def _create_simple_responsive_img(
        self,
        img_src: str,
        formats_data: dict[str, dict[int, str]],
        alt_text: str,
        class_attr: str,
        width: int,
        height: int,
    ) -> str:
        """Create a simple img tag with srcset (first format only)."""
        # Use first available format
        for format_name in self.config.formats:
            if format_name in formats_data and formats_data[format_name]:
                # Build srcset
                srcset_parts = []
                fallback_src = ""

                for size, path in sorted(formats_data[format_name].items()):
                    srcset_parts.append(f"{path} {size}w")
                    if not fallback_src:
                        fallback_src = path

                srcset = ", ".join(srcset_parts)
                loading_attr = (
                    ' loading="lazy" decoding="async"'
                    if self.config.add_loading_lazy
                    else ""
                )

                return (
                    f'<img src="{fallback_src}" '
                    f'srcset="{srcset}" '
                    f'sizes="{self.config.default_sizes}" '
                    f'alt="{alt_text}"{class_attr}{loading_attr} '
                    f'width="{width}" height="{height}">'
                )

        # Fallback to original if no formats processed
        return f'<img src="{img_src}" alt="{alt_text}"{class_attr}>'

    def _update_featured_photos(
        self,
        featured_photos: list[str],
        responsive_images: dict[str, dict[str, dict[int, str]]],
        ctx: PageContext,
    ) -> list[str]:
        """Update featured_photos to point to converted images (use largest size)."""
        updated_photos = []
        for photo in featured_photos:
            if photo in responsive_images and responsive_images[photo]:
                # Use first available format and largest size
                for format_name in self.config.formats:
                    if (
                        format_name in responsive_images[photo]
                        and responsive_images[photo][format_name]
                    ):
                        sizes = sorted(responsive_images[photo][format_name].keys())
                        largest_size = sizes[-1]
                        new_src = responsive_images[photo][format_name][largest_size]
                        updated_photos.append(new_src)
                        if self.config.verbose:
                            logger.debug(
                                f"Updated featured photo: {photo} -> {new_src}"
                            )
                        break
                else:
                    # Keep original if not processed
                    updated_photos.append(photo)
            else:
                # Keep original if not processed
                updated_photos.append(photo)
        return updated_photos
