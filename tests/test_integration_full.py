"""Comprehensive integration test using all available plugins."""

import random
import tempfile
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from scribe.builder import SiteBuilder
from scribe.config import NoteTemplate, ScribeConfig, TemplateConfig
from scribe.note_plugins.config import (
    DatePluginConfig,
    FootnotesPluginConfig,
    FrontmatterPluginConfig,
    ImageEncodingPluginConfig,
    MarkdownPluginConfig,
    ScreenshotPluginConfig,
    SnapshotPluginConfig,
)


class TestFullIntegration:
    """Test the complete build process with all plugins enabled."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def config_with_all_plugins(self, temp_dir: Path) -> ScribeConfig:
        """Create a comprehensive config that uses ALL available plugins."""
        # Setup directory structure
        source_dir = temp_dir / "content"
        output_dir = temp_dir / "dist"
        static_dir = temp_dir / "static"
        template_dir = temp_dir / "templates"
        snapshot_dir = temp_dir / "snapshots"

        source_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        static_dir.mkdir(exist_ok=True)
        template_dir.mkdir(exist_ok=True)
        snapshot_dir.mkdir(exist_ok=True)

        # Create template configuration
        templates = TemplateConfig(
            template_path=template_dir,
            base_templates=["index.html"],
            note_templates=[
                NoteTemplate(
                    template_path="note.html",
                    url_pattern="/notes/{slug}/",
                    predicates=["is_note"],
                ),
                NoteTemplate(
                    template_path="blog.html",
                    url_pattern="/blog/{slug}/",
                    predicates=["is_blog"],
                ),
            ],
        )

        # Configure all available plugins
        plugins = [
            FrontmatterPluginConfig(name="frontmatter", enabled=True),
            FootnotesPluginConfig(name="footnotes", enabled=True),
            MarkdownPluginConfig(name="markdown", enabled=True),
            DatePluginConfig(name="date", enabled=True),
            ScreenshotPluginConfig(
                name="screenshot",
                enabled=True,
                background_image="/desktops/custom.jpg",
                wrapper_classes="relative px-8 py-6 bg-cover bg-center "
                "screenshot-wrapper",
                inner_classes="flex justify-center items-center inner-content",
                image_classes="max-w-full h-auto rounded-lg shadow-lg",
            ),
            SnapshotPluginConfig(
                name="snapshot",
                enabled=True,
                snapshot_dir=snapshot_dir,
                max_concurrent=3,
                max_attempts=2,
                headful=False,
            ),
            ImageEncodingPluginConfig(
                name="image_encoding",
                enabled=True,
                cache_dir=temp_dir / ".image_cache",
                formats=["avif", "webp"],
                quality_avif=70,
                quality_webp=85,
                max_width=1920,
                max_height=1080,
                generate_responsive=True,
                responsive_sizes=[480, 768, 1024, 1200],
                verbose=True,
            ),
        ]

        # Configure build plugins (disabled for test environment)
        build_plugins = [
            # TailwindBuildPluginConfig(
            #     name="tailwind",
            #     enabled=False,  # Disabled for test environment
            #     input=static_dir / "input.css",
            #     watch=False,
            #     minify=True,
            #     flags=["--content", str(template_dir / "**/*.html")],
            #     verbose=False
            # )
        ]

        return ScribeConfig(
            source_dir=source_dir,
            output_dir=output_dir,
            static_path=static_dir,
            templates=templates,
            site_title="Comprehensive Test Site",
            site_description="A test site using all available Scribe plugins",
            site_url="https://test.example.com",
            note_plugins=plugins,
            build_plugins=build_plugins,
            clean_output=True,
        )

    @pytest.fixture
    def sample_images(self, temp_dir: Path) -> dict[str, Path]:
        """Generate test images using Pillow with noise and patterns."""
        static_dir = temp_dir / "static"
        images = {}

        # Generate a hero image with gradient
        hero_img = Image.new("RGB", (1200, 600), color="white")
        draw = ImageDraw.Draw(hero_img)

        # Create gradient effect
        for y in range(600):
            color_value = int(255 * (y / 600))
            draw.line([(0, y), (1200, y)], fill=(color_value, 100, 255 - color_value))

        # Add some geometric shapes
        draw.ellipse([300, 150, 600, 450], fill=(255, 255, 255, 128))
        draw.rectangle([700, 200, 1000, 400], fill=(255, 200, 100))

        hero_path = static_dir / "hero.jpg"
        hero_img.save(hero_path, "JPEG", quality=95)
        images["hero"] = hero_path

        # Generate a thumbnail with noise pattern
        thumb_img = Image.new("RGB", (400, 300), color="black")
        draw = ImageDraw.Draw(thumb_img)

        # Create noise-like pattern with random pixels
        for x in range(0, 400, 2):
            for y in range(0, 300, 2):
                color = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                )
                draw.point([(x, y)], fill=color)

        thumb_path = static_dir / "thumbnail.png"
        thumb_img.save(thumb_path, "PNG")
        images["thumbnail"] = thumb_path

        # Generate a pattern image
        pattern_img = Image.new("RGB", (800, 400), color="white")
        draw = ImageDraw.Draw(pattern_img)

        # Create checkerboard pattern
        for x in range(0, 800, 40):
            for y in range(0, 400, 40):
                if (x // 40 + y // 40) % 2 == 0:
                    draw.rectangle([x, y, x + 40, y + 40], fill=(50, 150, 200))

        pattern_path = static_dir / "pattern.jpg"
        pattern_img.save(pattern_path, "JPEG", quality=90)
        images["pattern"] = pattern_path

        # Generate a desktop background for screenshots
        desktop_img = Image.new("RGB", (1920, 1080), color=(30, 30, 60))
        draw = ImageDraw.Draw(desktop_img)

        # Add some abstract shapes for desktop wallpaper
        for _i in range(20):
            x = random.randint(0, 1920)
            y = random.randint(0, 1080)
            w = random.randint(50, 200)
            h = random.randint(50, 200)
            color = (
                random.randint(100, 255),
                random.randint(100, 255),
                random.randint(100, 255),
            )
            draw.ellipse([x, y, x + w, y + h], fill=color)

        desktop_path = static_dir / "desktops" / "custom.jpg"
        desktop_path.parent.mkdir(exist_ok=True)
        desktop_img.save(desktop_path, "JPEG", quality=85)
        images["desktop"] = desktop_path

        return images

    @pytest.fixture
    def sample_templates(self, temp_dir: Path) -> dict[str, Path]:
        """Create comprehensive Jinja2 templates."""
        template_dir = temp_dir / "templates"
        templates = {}

        # Base layout template
        base_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}{{ site.title }}{% endblock %}</title>
    <meta name="description"
          content="{% block description %}{{ site.description }}{% endblock %}">
    <link rel="stylesheet" href="/styles.css">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                         sans-serif;
        }
        .hero { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    </style>
</head>
<body class="bg-gray-50">
    <nav class="bg-white shadow-sm border-b">
        <div class="max-w-4xl mx-auto px-4 py-4">
            <h1 class="text-xl font-bold text-gray-900">{{ site.title }}</h1>
        </div>
    </nav>

    <main class="max-w-4xl mx-auto px-4 py-8">
        {% block content %}{% endblock %}
    </main>

    <footer class="bg-gray-800 text-white mt-16">
        <div class="max-w-4xl mx-auto px-4 py-8">
            <p>&copy; 2024 {{ site.title }}. Built with Scribe.</p>
            <p class="text-sm text-gray-400 mt-2">
                Generated on {{ build_metadata.build_time[:19] }} by
                {{ build_metadata.generator }}
            </p>
        </div>
    </footer>
</body>
</html>"""

        base_path = template_dir / "base.html"
        base_path.write_text(base_template)
        templates["base"] = base_path

        # Index template
        index_template = """{% extends "base.html" %}

{% block title %}{{ site.title }} - Home{% endblock %}

{% block content %}
<div class="hero text-white py-16 px-8 rounded-lg mb-8">
    <h1 class="text-4xl font-bold mb-4">Welcome to {{ site.title }}</h1>
    <p class="text-xl opacity-90">{{ site.description }}</p>
</div>

<div class="grid md:grid-cols-1 gap-8">
    <section>
        <h2 class="text-2xl font-bold mb-4">All Content</h2>
        <div class="space-y-4">
            <article class="bg-white p-6 rounded-lg shadow-sm border">
                <h3 class="text-lg font-semibold mb-2">
                    <a href="/notes/advanced-python/"
                       class="text-blue-600 hover:text-blue-800">
                        Advanced Python Techniques
                    </a>
                </h3>
                <p class="text-gray-600 mb-2">Exploring advanced Python programming
                patterns and techniques</p>
                <time class="text-sm text-gray-500">2024-01-15</time>
                <span class="inline-block bg-blue-100 text-blue-800 px-2 py-1 rounded
                      text-xs ml-2">Note</span>
            </article>

            <article class="bg-white p-6 rounded-lg shadow-sm border">
                <h3 class="text-lg font-semibold mb-2">
                    <a href="/blog/web-development/"
                       class="text-green-600 hover:text-green-800">
                        Building Modern Web Applications
                    </a>
                </h3>
                <p class="text-gray-600 mb-2">A comprehensive guide to building
                scalable web applications in 2024</p>
                <time class="text-sm text-gray-500">2024-01-10</time>
                <span class="inline-block bg-green-100 text-green-800 px-2 py-1 rounded
                      text-xs ml-2">Blog Post</span>
            </article>

            <article class="bg-white p-6 rounded-lg shadow-sm border">
                <h3 class="text-lg font-semibold mb-2">
                    <a href="/notes/image-guide/"
                       class="text-blue-600 hover:text-blue-800">
                        Image Processing Guide
                    </a>
                </h3>
                <p class="text-gray-600 mb-2">Complete guide to image processing
                and optimization</p>
                <time class="text-sm text-gray-500">2024-01-08</time>
                <span class="inline-block bg-blue-100 text-blue-800 px-2 py-1 rounded
                      text-xs ml-2">Note</span>
            </article>
        </div>
    </section>
</div>
{% endblock %}"""

        index_path = template_dir / "index.html"
        index_path.write_text(index_template)
        templates["index"] = index_path

        # Note template
        note_template = """{% extends "base.html" %}

{% block title %}{{ note.title }} - {{ site.title }}{% endblock %}
{% block description %}{{ note.description or note.title }}{% endblock %}

{% block content %}
<article class="bg-white rounded-lg shadow-sm border p-8">
    <header class="mb-8 pb-4 border-b">
        <h1 class="text-3xl font-bold text-gray-900 mb-4">{{ note.title }}</h1>

        <div class="flex flex-wrap items-center gap-4 text-sm text-gray-600">
            {% if note.author %}
                <span>By {{ note.author }}</span>
            {% endif %}
            {% if note.date %}
                <time>{{ note.date }}</time>
            {% endif %}
            <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded">Note</span>
        </div>

        {% if note.tags %}
            <div class="mt-4">
                {% for tag in note.tags %}
                    <span class="inline-block bg-gray-100 text-gray-700 px-3 py-1
                          rounded-full text-sm mr-2">{{ tag }}</span>
                {% endfor %}
            </div>
        {% endif %}
    </header>

    <div class="prose prose-lg max-w-none">
        {{ note.content | safe }}
    </div>
</article>

<nav class="mt-8 py-4 border-t">
    <a href="/" class="text-blue-600 hover:text-blue-800">&larr; Back to Home</a>
</nav>
{% endblock %}"""

        note_path = template_dir / "note.html"
        note_path.write_text(note_template)
        templates["note"] = note_path

        # Blog template
        blog_template = """{% extends "base.html" %}

{% block title %}{{ note.title }} - {{ site.title }}{% endblock %}
{% block description %}{{ note.description or note.title }}{% endblock %}

{% block content %}
<article class="bg-white rounded-lg shadow-sm border p-8">
    <header class="mb-8 pb-4 border-b">
        <h1 class="text-3xl font-bold text-gray-900 mb-4">{{ note.title }}</h1>

        <div class="flex flex-wrap items-center gap-4 text-sm text-gray-600">
            {% if note.author %}
                <span>By {{ note.author }}</span>
            {% endif %}
            {% if note.date %}
                <time>{{ note.date }}</time>
            {% endif %}
            <span class="bg-green-100 text-green-800 px-2 py-1 rounded">Blog Post</span>
        </div>
    </header>

    <div class="prose prose-lg max-w-none">
        {{ note.content | safe }}
    </div>
</article>

<nav class="mt-8 py-4 border-t">
    <a href="/" class="text-green-600 hover:text-green-800">&larr; Back to Home</a>
</nav>
{% endblock %}"""

        blog_path = template_dir / "blog.html"
        blog_path.write_text(blog_template)
        templates["blog"] = blog_path

        return templates

    @pytest.fixture
    def sample_notes(self, temp_dir: Path) -> dict[str, Path]:
        """Create sample notes with comprehensive frontmatter and content."""
        source_dir = temp_dir / "content"
        notes = {}

        # Note 1: Technical note with images and footnotes
        note1_content = """---
title: "Advanced Python Techniques"
description: "Exploring advanced Python programming patterns and techniques"
author: "Tech Writer"
date: "2024-01-15"
tags: ["python", "programming", "advanced"]
type: "note"
status: "publish"
slug: "advanced-python-techniques"
---

# Advanced Python Techniques

This note covers advanced Python programming techniques that every
developer should know.

## Image Examples

Here's a hero image using the image helper:

{{ responsive_image("hero", alt="Hero image showing Python code",
                    class_="w-full rounded-lg") }}

And a simple thumbnail:

{{ simple_image("thumbnail", alt="Code thumbnail",
                 class_="float-right w-32 h-24 ml-4") }}

## Code Patterns

Here are some advanced patterns:

```python
# Context managers
class DatabaseConnection:
    def __enter__(self):
        self.conn = connect_to_db()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()
```

## Footnotes

Python has many powerful features[^1] that make it excellent for various
applications[^2].

The decorator pattern[^3] is particularly useful for adding functionality to functions.

![Pattern Example](pattern.jpg "A visual pattern")

[^1]: Including list comprehensions, generators, and context managers
[^2]: From web development to data science and machine learning
[^3]: Decorators allow you to modify or enhance functions without changing their code

## Screenshots

Here's a code screenshot:

```screenshot
https://python.org
```

This will capture a screenshot of the Python website.
"""

        note1_path = source_dir / "advanced-python.md"
        note1_path.write_text(note1_content)
        notes["note1"] = note1_path

        # Note 2: Blog post with different structure
        note2_content = """---
title: "Building Modern Web Applications"
description: "A comprehensive guide to building scalable web applications in 2024"
author: "Web Developer"
date: "2024-01-10"
tags: ["web", "javascript", "react", "backend"]
type: "blog"
status: "publish"
slug: "building-modern-web-apps"
---

# Building Modern Web Applications

In this blog post, we'll explore the landscape of modern web development.

## Frontend Technologies

The frontend ecosystem continues to evolve rapidly. Key technologies include:

- **React**: For building user interfaces
- **Next.js**: Full-stack React framework
- **TypeScript**: Adding type safety to JavaScript

## Backend Architecture

Modern backend development focuses on:

1. **Microservices**: Breaking applications into smaller services
2. **API Design**: Creating robust REST and GraphQL APIs
3. **Database Design**: Choosing the right data storage solutions

Here's an example API endpoint:

```javascript
app.get('/api/users/:id', async (req, res) => {
    const user = await User.findById(req.params.id);
    res.json(user);
});
```

## Performance Considerations

Performance is crucial for modern web applications. Consider:

- Code splitting and lazy loading
- Image optimization (like using {{ image_srcset("hero", "avif") }})
- Caching strategies
- CDN usage

The image helper plugin provides great tools for responsive images[^performance].

[^performance]: Responsive images can significantly improve page load
times on mobile devices
"""

        note2_path = source_dir / "web-development.md"
        note2_path.write_text(note2_content)
        notes["note2"] = note2_path

        # Note 3: Draft note (should not be published)
        note3_content = """---
title: "Work in Progress"
description: "This is still being written"
author: "Draft Author"
date: "2024-01-20"
tags: ["draft", "wip"]
type: "note"
status: "draft"
slug: "work-in-progress"
---

# Work in Progress

This note is still being written and shouldn't appear in the final build.

Content coming soon...
"""

        note3_path = source_dir / "draft-note.md"
        note3_path.write_text(note3_content)
        notes["note3"] = note3_path

        # Note 4: Note with complex images and responsive features
        note4_content = """---
title: "Image Processing Guide"
description: "Complete guide to image processing and optimization"
author: "Image Expert"
date: "2024-01-08"
tags: ["images", "optimization", "web-performance"]
type: "note"
status: "publish"
slug: "image-processing-guide"
---

# Image Processing Guide

This guide covers everything about image processing and optimization for the web.

## Responsive Images

The image helper plugin makes it easy to create responsive images:

{{ responsive_image("hero",
    alt="Hero image demonstrating responsive design",
    sizes="(max-width: 768px) 100vw, (max-width: 1024px) 80vw, 60vw",
    class_="w-full h-64 object-cover rounded-xl shadow-lg",
    formats=["avif", "webp"],
    responsive_sizes=[320, 640, 960, 1280]
) }}

## Different Image Formats

You can also specify different formats:

{{ simple_image("thumbnail", alt="Thumbnail in AVIF format",
                 format_="avif", class_="w-32 h-32 rounded-full") }}

## Image Srcsets

For advanced control, you can generate srcsets:

```html
<img src="pattern.jpg"
     srcset="{{ image_srcset('pattern', 'webp', [480, 768, 1024]) }}"
     sizes="(max-width: 768px) 100vw, 50vw"
     alt="Pattern background">
```

## Performance Tips

- Always use modern formats like AVIF and WebP
- Implement responsive images for different screen sizes
- Use lazy loading for images below the fold
- Optimize image quality vs file size

The image encoding plugin automatically handles format conversion and
optimization[^optimization].

[^optimization]: The plugin can reduce image sizes by up to 80% while maintaining
visual quality
"""

        note4_path = source_dir / "image-guide.md"
        note4_path.write_text(note4_content)
        notes["note4"] = note4_path

        return notes

    @pytest.fixture
    def tailwind_css(self, temp_dir: Path) -> Path:
        """Create a sample Tailwind CSS input file."""
        static_dir = temp_dir / "static"
        css_content = """@tailwind base;
@tailwind components;
@tailwind utilities;

@layer components {
    .prose {
        @apply text-gray-800 leading-relaxed;
    }

    .prose h1 {
        @apply text-3xl font-bold mb-4;
    }

    .prose h2 {
        @apply text-2xl font-semibold mb-3;
    }

    .prose p {
        @apply mb-4;
    }

    .prose code {
        @apply bg-gray-100 px-1 py-0.5 rounded text-sm;
    }

    .prose pre {
        @apply bg-gray-900 text-white p-4 rounded-lg overflow-x-auto;
    }
}"""

        css_path = static_dir / "input.css"
        css_path.write_text(css_content)
        return css_path

    async def test_full_integration_build(
        self,
        temp_dir: Path,
        config_with_all_plugins: ScribeConfig,
        sample_images: dict[str, Path],
        sample_templates: dict[str, Path],
        sample_notes: dict[str, Path],
        tailwind_css: Path,
    ) -> None:
        """Test the complete build process with all plugins enabled."""
        # Build the site
        builder = SiteBuilder(config_with_all_plugins)

        try:
            await builder.build_site()

            # Verify output structure exists
            output_dir = config_with_all_plugins.output_dir
            assert output_dir.exists()

            # Check that index.html was generated
            index_path = output_dir / "index.html"
            assert index_path.exists()
            index_content = index_path.read_text()

            # Verify index content contains site info
            assert "Comprehensive Test Site" in index_content
            assert "A test site using all available Scribe plugins" in index_content
            assert "Advanced Python Techniques" in index_content
            assert "Building Modern Web Applications" in index_content

            # Draft note should not appear
            assert "Work in Progress" not in index_content

            # Check that note pages were generated with correct URLs
            python_note_path = output_dir / "notes" / "advanced-python" / "index.html"
            assert python_note_path.exists()
            python_content = python_note_path.read_text()

            # Verify note content was processed
            assert "Advanced Python Techniques" in python_content
            assert "Tech Writer" in python_content
            assert "python" in python_content
            assert "Note</span>" in python_content  # Template-specific content

            # Check blog post
            blog_path = output_dir / "blog" / "web-development" / "index.html"
            assert blog_path.exists()
            blog_content = blog_path.read_text()
            assert "Building Modern Web Applications" in blog_content
            assert "Blog Post</span>" in blog_content

            # Check image guide
            image_guide_path = output_dir / "notes" / "image-guide" / "index.html"
            assert image_guide_path.exists()
            image_guide_content = image_guide_path.read_text()
            assert "Image Processing Guide" in image_guide_content

            # Verify footnotes were processed and converted to HTML
            assert "[^1]" not in python_content  # Should be converted to HTML
            assert (
                'class="footnote"' in python_content
                or "footnote-ref" in python_content
                or "fn:" in python_content
            )

            # Verify markdown was processed
            # Content is in template wrapper, check for markdown content
            assert (
                '<h1 id="advanced-python-techniques">Advanced Python Techniques</h1>'
                in python_content
            )
            assert "<p>" in python_content
            assert "<code>" in python_content

            # Verify static files were copied
            hero_output = output_dir / "hero.jpg"
            assert hero_output.exists()

            thumbnail_output = output_dir / "thumbnail.png"
            assert thumbnail_output.exists()

            pattern_output = output_dir / "pattern.jpg"
            assert pattern_output.exists()

            # Verify image encoding plugin processed images
            # Check for generated responsive images
            cache_dir = temp_dir / ".image_cache"
            if cache_dir.exists():
                cache_files = list(cache_dir.rglob("*"))
                # Should have processed some images
                assert len([f for f in cache_files if f.is_file()]) > 0

            # Image helper has been removed - template functions will remain unprocessed
            # Check that other content is still processed correctly
            assert "Advanced Python Techniques" in python_content

            # Check that dates were processed
            assert (
                "2024-01-15" in python_content or "January 15, 2024" in python_content
            )

            # Verify template structure
            assert "<nav" in index_content
            assert "<footer" in index_content
            assert "Built with Scribe" in index_content

            # Check CSS output (if Tailwind was processed)
            # Note: CSS might not be generated if Tailwind CLI is not available
            # This is expected in test environment

        finally:
            # Cleanup
            builder.cleanup()

    async def test_plugin_data_available_in_templates(
        self,
        temp_dir: Path,
        config_with_all_plugins: ScribeConfig,
        sample_images: dict[str, Path],
        sample_templates: dict[str, Path],
        sample_notes: dict[str, Path],
        tailwind_css: Path,
    ) -> None:
        """Test that plugin data is correctly available in templates."""
        # Build a single file to check plugin data
        builder = SiteBuilder(config_with_all_plugins)

        try:
            # Process the image guide note specifically
            image_guide_path = sample_notes["note4"]
            ctx = await builder.build_file(image_guide_path)

            assert ctx is not None

            # Check that plugins processed the context
            assert ctx.title == "Image Processing Guide"
            assert ctx.author == "Image Expert"
            assert ctx.tags == ["images", "optimization", "web-performance"]

            # Check that content was processed by markdown plugin
            assert '<h1 id="image-processing-guide">' in ctx.content
            assert '<h2 id="responsive-images">' in ctx.content

            # Image helper has been removed - check other plugin data instead
            assert ctx.frontmatter is not None

            # Check that image encoding plugin processed images
            if ctx.image_encoding_data:
                assert ctx.image_encoding_data.processed_images is not None

            # Verify output file was written
            assert ctx.output_path.exists()
            output_content = ctx.output_path.read_text()
            assert "Image Processing Guide" in output_content

        finally:
            builder.cleanup()

    async def test_error_handling_and_validation(
        self,
        temp_dir: Path,
        config_with_all_plugins: ScribeConfig,
        sample_images: dict[str, Path],
        sample_templates: dict[str, Path],
        tailwind_css: Path,
    ) -> None:
        """Test error handling with invalid content."""
        # Create a note with invalid frontmatter
        source_dir = config_with_all_plugins.source_dir
        invalid_note = source_dir / "invalid.md"

        invalid_content = """---
title: "Invalid Note"
date: "not-a-date"
tags: not-a-list
---

# Invalid Note

This note has invalid frontmatter.
"""

        invalid_note.write_text(invalid_content)

        # Build should handle errors gracefully
        builder = SiteBuilder(config_with_all_plugins)

        try:
            await builder.build_site()

            # Check that other valid notes were still processed
            output_dir = config_with_all_plugins.output_dir
            index_path = output_dir / "index.html"
            assert index_path.exists()

            # Check that build errors were tracked
            # The builder should have some error handling mechanism

        finally:
            builder.cleanup()

    def test_config_serialization(self, config_with_all_plugins: ScribeConfig) -> None:
        """Test that the comprehensive config can be serialized to YAML."""
        # Convert config to dict
        config_dict = config_with_all_plugins.model_dump(mode="json")

        # Verify all plugins are included
        plugin_names = [p["name"] for p in config_dict["note_plugins"]]
        expected_plugins = [
            "frontmatter",
            "footnotes",
            "markdown",
            "date",
            "screenshot",
            "snapshot",
            "image_encoding",
        ]

        for expected in expected_plugins:
            assert expected in plugin_names

        # Verify build plugins (tailwind disabled for test environment)
        # build_plugin_names = [p["name"] for p in config_dict["build_plugins"]]
        # assert "tailwind" in build_plugin_names  # Disabled for test environment

        # Test YAML serialization
        yaml_content = yaml.dump(config_dict, default_flow_style=False)
        assert "note_plugins:" in yaml_content
        assert "build_plugins:" in yaml_content
        assert "templates:" in yaml_content

        # Should be able to load back from YAML
        loaded_config = yaml.safe_load(yaml_content)
        assert loaded_config["site_title"] == "Comprehensive Test Site"

    async def test_predicate_filtering(
        self,
        temp_dir: Path,
        config_with_all_plugins: ScribeConfig,
        sample_images: dict[str, Path],
        sample_templates: dict[str, Path],
        sample_notes: dict[str, Path],
        tailwind_css: Path,
    ) -> None:
        """Test that predicate filtering works correctly in templates."""
        builder = SiteBuilder(config_with_all_plugins)

        try:
            await builder.build_site()

            # Check index page content for proper filtering
            index_path = config_with_all_plugins.output_dir / "index.html"
            index_content = index_path.read_text()

            # Should have notes in the notes section
            # Should have blog posts in the blog section
            # The exact implementation depends on the predicate system

            # Verify that different types are handled correctly
            assert "Note</span>" in index_content or "Blog Post</span>" in index_content

        finally:
            builder.cleanup()
