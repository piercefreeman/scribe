"""Image encoding plugin for processing images referenced in page content."""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pyvips

if TYPE_CHECKING:
    from scribe.config import ScribeConfig

from scribe.context import ImageEncodingData, PageContext
from scribe.logger import get_logger
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import ImageEncodingPluginConfig, PluginName

logger = get_logger(__name__)


class ImageEncodingPlugin(NotePlugin[ImageEncodingPluginConfig]):
    """Plugin that processes and optimizes images with responsive sizing using WebP."""

    name = PluginName.IMAGE_ENCODING

    def __init__(
        self,
        config: ImageEncodingPluginConfig,
        global_config: "ScribeConfig",
    ) -> None:
        super().__init__(config)
        self.global_config = global_config
        self.supports_webp = self._test_webp_support()

        if self.supports_webp:
            logger.info("WebP encoding is supported")
        else:
            logger.warning("WebP encoding is not supported by libvips")

    def _test_webp_support(self) -> bool:
        """Test if libvips supports WebP encoding."""
        try:
            # Create a small test image and try to encode it to WebP
            test_img = pyvips.Image.black(10, 10, bands=3)
            with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp_file:
                # Try to encode using write_to_file with .webp extension
                test_img.write_to_file(tmp_file.name, Q=80)
                os.unlink(tmp_file.name)
            return True
        except Exception as e:
            logger.debug(f"WebP not supported: {e}")
            return False

    async def process(self, ctx: PageContext) -> PageContext:
        """Process images referenced in the page content."""
        if not self.supports_webp:
            logger.warning("WebP not supported, skipping image processing")
            return ctx

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
        responsive_images = {}
        image_dimensions = {}

        for img_src in image_refs:
            try:
                result = await self._process_image_responsive(img_src, cache_dir, ctx)
                if result:
                    responsive_data, dimensions = result
                    responsive_images[img_src] = responsive_data
                    image_dimensions[img_src] = dimensions
            except Exception as e:
                logger.error(f"Error processing {img_src}: {e}")

        # Store processed image info as typed attribute
        ctx.image_encoding_data = ImageEncodingData(
            processed_images={k: ["webp"] for k in responsive_images.keys()},
            formats=["webp"],
            responsive_images=responsive_images,
            image_dimensions=image_dimensions,
        )

        # Rewrite HTML image tags to use picture elements
        if responsive_images:
            ctx.content = self._rewrite_html_to_responsive_images(
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
    ) -> tuple[dict[int, str], tuple[int, int]] | None:
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
            img = pyvips.Image.new_from_file(str(source_path), access="sequential")
            # Convert and orient the image
            img = self._prepare_image(img)
            original_dimensions = img.width, img.height

            # Generate responsive sizes
            responsive_data = {}
            sizes_to_generate = []

            if self.config.generate_responsive:
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
            else:
                # Just use original size
                sizes_to_generate.append(img.width)

            # Generate all sizes
            for size in sizes_to_generate:
                if self._process_responsive_size(
                    img, size, source_path, image_cache_dir, ctx
                ):
                    responsive_data[size] = self._get_responsive_path(
                        source_path, size, ctx
                    )

            # Copy cache to output
            await self._copy_cache_to_output(image_cache_dir, source_path, ctx)

            return responsive_data, original_dimensions

        except Exception as e:
            logger.error(f"Error processing image {source_path}: {e}")
            return None

    def _process_responsive_size(
        self,
        img: pyvips.Image,
        target_width: int,
        source_path: Path,
        cache_dir: Path,
        ctx: PageContext,
    ) -> bool:
        """Process image to a specific width."""
        try:
            # Skip if target width is larger than original
            if target_width > img.width:
                return False

            # For each size, load the image fresh to avoid memory issues
            fresh_img = pyvips.Image.new_from_file(str(source_path), access="sequential")
            fresh_img = self._prepare_image(fresh_img)

            # Resize image maintaining aspect ratio or use original
            if target_width == fresh_img.width:
                processed_img = fresh_img
            else:
                scale = target_width / fresh_img.width
                processed_img = fresh_img.resize(scale)

            # Apply max_height constraint if specified
            if self.config.max_height and processed_img.height > self.config.max_height:
                scale = self.config.max_height / processed_img.height
                processed_img = processed_img.resize(scale)

            # Save to cache using consistent naming that matches parsing logic
            base_name = ctx.generate_slug_from_text(source_path.stem)
            output_file = cache_dir / f"{base_name}-{target_width}.webp"

            if self.config.verbose:
                logger.debug(f"Saving WebP file: {output_file}")

            # Use the most conservative approach: ensure image is fully computed
            # Force the image to be fully realized in memory
            processed_img = processed_img.copy()
            
            # Save as WebP using the most basic approach
            processed_img.webpsave(str(output_file), Q=self.config.quality_webp, lossless=False)
            
            return True

        except Exception as e:
            logger.error(f"Error processing image at {target_width}w: {e}")
            return False

    def _get_cached_responsive_data(
        self, cache_dir: Path, source_path: Path, ctx: PageContext
    ) -> tuple[dict[int, str], tuple[int, int]]:
        """Get responsive data from cached files."""
        responsive_data = {}
        original_dimensions = (1024, 768)  # fallback

        # Get naming components for new convention
        image_name = ctx.generate_slug_from_text(source_path.stem)
        page_slug = ctx.slug or "untitled"

        # Find all cached WebP files
        for cached_file in cache_dir.glob("*.webp"):
            # Extract width from filename (e.g., "image-480.webp" -> 480)
            name_part = cached_file.stem
            if "-" in name_part:
                try:
                    width = int(name_part.split("-")[-1])
                    # Generate URL using new naming convention
                    filename = f"{page_slug}_{image_name}_{width}.webp"
                    path = f"/images/{filename}"
                    responsive_data[width] = path
                except ValueError:
                    # Fallback for non-responsive files
                    filename = f"{page_slug}_{image_name}.webp"
                    path = f"/images/{filename}"
                    responsive_data[1024] = path

        return responsive_data, original_dimensions

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

    def _prepare_image(self, img: pyvips.Image) -> pyvips.Image:
        """Prepare image for processing."""
        # Apply auto-rotation based on EXIF orientation first
        try:
            # Get the orientation from EXIF data
            orientation = img.get("orientation")
            if orientation and orientation != 1:
                img = img.autorot()
        except pyvips.Error:
            # No orientation data, which is fine
            pass

        # Ensure we have the right number of bands and format
        if img.bands == 1:
            # Convert grayscale to RGB
            img = img.colourspace("srgb")
        elif img.bands == 4:
            # Convert RGBA to RGB by flattening with white background
            img = img.flatten(background=[255, 255, 255])
        elif img.bands > 4:
            # Take only the first 3 bands if there are more than 4
            img = img[:3]

        # Ensure we have exactly 3 bands (RGB)
        if img.bands != 3:
            img = img.colourspace("srgb")

        # Convert to sequential access for better memory efficiency with large images
        img = img.copy()

        return img

    async def _copy_cache_to_output(
        self, cache_dir: Path, source_path: Path, ctx: PageContext
    ) -> None:
        """Copy the entire cache directory to output."""
        if not self.global_config or not cache_dir.exists():
            return

        try:
            # Output to /images/ directory with new naming convention
            output_dir = self.global_config.output_dir / "images"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Get naming components
            image_name = ctx.generate_slug_from_text(source_path.stem)
            page_slug = ctx.slug or "untitled"

            # Copy all files from cache to output with new naming
            for cached_file in cache_dir.glob("*"):
                if cached_file.is_file():
                    # Extract width from cached filename (e.g., "image-480.webp" -> 480)
                    name_part = cached_file.stem
                    if "-" in name_part:
                        try:
                            width = int(name_part.split("-")[-1])
                            new_filename = f"{page_slug}_{image_name}_{width}.webp"
                        except ValueError:
                            # Fallback for non-responsive files
                            new_filename = f"{page_slug}_{image_name}.webp"
                    else:
                        new_filename = f"{page_slug}_{image_name}.webp"

                    output_file = output_dir / new_filename
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
        self, source_path: Path, width: int, ctx: PageContext
    ) -> str:
        """Get the responsive image path for a given source image and width."""
        # Get the base name without extension and convert to proper slug
        image_name = ctx.generate_slug_from_text(source_path.stem)
        page_slug = ctx.slug or "untitled"

        # New naming convention: /images/{slug}_{image_name}_{resizing}.webp
        filename = f"{page_slug}_{image_name}_{width}.webp"
        path = f"/images/{filename}"

        return path

    def _rewrite_html_to_responsive_images(
        self,
        content: str,
        responsive_images: dict[str, dict[int, str]],
        image_dimensions: dict[str, tuple[int, int]],
        ctx: PageContext,
    ) -> str:
        """Rewrite HTML img tags to use responsive images."""

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

            if self.config.use_picture_element:
                # Full picture element with WebP source
                return self._create_picture_element(
                    responsive_images[img_src],
                    alt_text,
                    class_attr,
                    width,
                    height,
                )
            else:
                # Simple img tag with srcset
                return self._create_responsive_img(
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
        responsive_data: dict[int, str],
        alt_text: str,
        class_attr: str,
        width: int,
        height: int,
    ) -> str:
        """Create a picture element with WebP source."""
        if not responsive_data:
            return f'<img src="" alt="{alt_text}"{class_attr}>'

        # Build srcset for WebP
        srcset_parts = []
        for size, path in sorted(responsive_data.items()):
            srcset_parts.append(f"{path} {size}w")

        srcset = ", ".join(srcset_parts)

        # Use the largest size as fallback
        sizes = sorted(responsive_data.keys())
        fallback_size = sizes[-1] if len(sizes) == 1 else sizes[len(sizes) // 2]
        fallback_src = responsive_data[fallback_size]

        # Create picture element
        loading_attr = (
            ' loading="lazy" decoding="async"' if self.config.add_loading_lazy else ""
        )

        picture_html = f"""<picture>
  <source type="image/webp" srcset="{srcset}" sizes="{self.config.default_sizes}">
  <img src="{fallback_src}" alt="{alt_text}"{class_attr}{loading_attr}
       width="{width}" height="{height}">
</picture>"""

        return picture_html

    def _create_responsive_img(
        self,
        responsive_data: dict[int, str],
        alt_text: str,
        class_attr: str,
        width: int,
        height: int,
    ) -> str:
        """Create a simple img tag with srcset."""
        if not responsive_data:
            return f'<img src="" alt="{alt_text}"{class_attr}>'

        # Build srcset
        srcset_parts = []
        fallback_src = ""

        for size, path in sorted(responsive_data.items()):
            srcset_parts.append(f"{path} {size}w")
            if not fallback_src:
                fallback_src = path

        srcset = ", ".join(srcset_parts)
        loading_attr = (
            ' loading="lazy" decoding="async"' if self.config.add_loading_lazy else ""
        )

        return (
            f'<img src="{fallback_src}" '
            f'srcset="{srcset}" '
            f'sizes="{self.config.default_sizes}" '
            f'alt="{alt_text}"{class_attr}{loading_attr} '
            f'width="{width}" height="{height}">'
        )

    def _update_featured_photos(
        self,
        featured_photos: list[str],
        responsive_images: dict[str, dict[int, str]],
        ctx: PageContext,
    ) -> list[str]:
        """Update featured_photos to point to converted images (use largest size)."""
        updated_photos = []
        for photo in featured_photos:
            if photo in responsive_images and responsive_images[photo]:
                # Use largest size
                sizes = sorted(responsive_images[photo].keys())
                largest_size = sizes[-1]
                new_src = responsive_images[photo][largest_size]
                updated_photos.append(new_src)
                if self.config.verbose:
                    logger.debug(f"Updated featured photo: {photo} -> {new_src}")
            else:
                # Keep original if not processed
                updated_photos.append(photo)
        return updated_photos
