# Scribe

A static site generator with an extendable plugin architecture. I use this to power [pierce.dev](https://pierce.dev).

## Features

- **Fast**: Built with asyncio for concurrent processing
- **Modular**: Flexible plugin architecture for extensibility
- **Developer-friendly**: Hot reloading with `watchfiles` and live preview
- **Configurable**: YAML configuration with sensible defaults

## Installation

```bash
pip install scribe
```

## Quick Start

1. Initialize a new project:
```bash
scribe init
```

2. Start the development server:
```bash
scribe dev
```

3. Open your browser to `http://localhost:8000`

## CLI Commands

- `scribe init` - Initialize a new project
- `scribe build --output <dir>` - Build the static site to specified directory
- `scribe dev` - Start development server with file watching and auto-rebuild
- `scribe add-headers` - Add frontmatter headers to markdown files that don't have them
- `scribe config` - Show current configuration

## Configuration

Configuration is stored in `~/.scribe/config.yml`:

```yaml
source_dir: ./content
output_dir: ./dist
site_title: My Site
site_description: A great site
host: 127.0.0.1
port: 8000
note_plugins:
  - name: frontmatter
    enabled: true
  - name: markdown
    enabled: true
templates:
  template_path: ./templates
  base_templates:
    - index.j2
    - about.j2
  note_templates:
    - template_path: blog_post.j2
      url_pattern: /blog/{slug}/
      predicates:
        - is_published
        - has_tag:blog
static_path: ./static
```

## Plugin Architecture

Scribe uses a flexible plugin system where each markdown file is processed through a chain of plugins. Each plugin receives a `PageContext` object containing metadata and content.

### Built-in Plugins

- **FrontmatterPlugin**: Extracts YAML frontmatter from markdown files
- **MarkdownPlugin**: Converts markdown to HTML
- **SlugPlugin**: Generates URL slugs
- **DatePlugin**: Parses and formats dates

### Creating Custom Plugins

```python
from scribe.plugins.base import Plugin
from scribe.context import PageContext

class MyPlugin(Plugin):
    async def process(self, ctx: PageContext) -> PageContext:
        # Process the context
        return ctx
```

## Markdown Document Headers

Scribe supports YAML frontmatter headers in markdown documents for metadata and configuration.

### Header Format

Use standard YAML frontmatter with `---` delimiters at the beginning of your markdown files:

```markdown
---
title: "My Blog Post"
description: "A comprehensive guide to something amazing"
author: "John Doe"
date: "2024-01-15"
tags: ["python", "web-development", "static-sites"]
draft: false
slug: "my-custom-slug"
---

# Your content title

Your markdown content goes here...
```

### Supported Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Page title (can be overridden by markdown `#` header) |
| `description` | string | Meta description for SEO |
| `author` | string | Author name |
| `date` | string | Publication date (formats: YYYY-MM-DD, YYYY-MM-DD HH:MM:SS, YYYY/MM/DD) |
| `tags` | list/string | Tags as array or comma-separated string |
| `slug` | string | Custom URL slug (auto-generated from filename if not provided) |
| `template` | string | Specific template to use for this page |
| `layout` | string | Layout specification |
| `draft` | boolean | Whether the page is a draft (excludes from `is_published` predicate) |
| `permalink` | string | Custom permalink override |

### Processing Behavior

1. **Title Priority**: Markdown headers (`# Title`) override frontmatter titles
2. **Tag Formats**: Tags can be specified as `["tag1", "tag2"]` or `"tag1, tag2"`
3. **Date Parsing**: Multiple date formats supported with intelligent fallback
4. **Auto-generation**: Missing slugs and URLs are automatically generated from filenames
5. **Template Access**: All frontmatter data is available in templates via `note.frontmatter`

## Template System

Scribe uses Jinja2 templates for rendering HTML pages. Templates are configured in your `config.yml` file.

### Template Types

- **Base Templates**: Standalone templates that render 1:1 to HTML files with global site context
- **Note Templates**: Templates that wrap individual markdown notes with filtering predicates

### Template Variables

All templates receive the following variables:

| Variable | Type | Description |
|----------|------|-------------|
| `site.title` | string | Site title from configuration |
| `site.description` | string | Site description from configuration |
| `site.url` | string | Base URL for the site |
| `config` | dict | Full configuration object |

### Note Template Variables

Note templates additionally receive a `note` object with the following properties:

| Variable | Type | Description |
|----------|------|-------------|
| `note.title` | string | Page title from frontmatter or filename |
| `note.content` | string | Rendered HTML content |
| `note.author` | string | Author from frontmatter |
| `note.date` | string | Formatted date |
| `note.tags` | list | List of tags from frontmatter |
| `note.description` | string | Meta description |
| `note.slug` | string | URL slug |
| `note.url` | string | Full URL path |
| `note.is_draft` | boolean | Whether the note is a draft |
| `note.frontmatter` | dict | Raw frontmatter data |
| `note.source_path` | string | Path to source markdown file |
| `note.relative_path` | string | Relative path from source directory |
| `note.modified_time` | float | File modification timestamp |

### Template Predicates

Filter which notes match templates using predicates:

| Predicate | Description |
|-----------|-------------|
| `all` | Matches all notes |
| `is_published` | Matches non-draft notes |
| `is_draft` | Matches draft notes only |
| `has_tag:tagname` | Matches notes with specific tag |

## Static Files

Scribe can copy static files (CSS, JavaScript, images, etc.) directly to the output directory without processing.

Configure the `static_path` in your config to specify a directory containing static assets:

```yaml
static_path: ./static
```

### How It Works

- All files in the `static_path` directory are copied recursively to the output directory
- Files are only copied if they don't exist or are newer than the existing file
- Directory structures are preserved and merged with generated content
- Static files can coexist with generated HTML files in the same directories

## License

MIT License