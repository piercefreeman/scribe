"""Tests for template context generation."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from scribe.builder import SiteBuilder
from scribe.config import ScribeConfig, TemplateConfig


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create directories
        content_dir = project_dir / "content"
        templates_dir = project_dir / "templates"
        output_dir = project_dir / "dist"

        content_dir.mkdir()
        templates_dir.mkdir()
        output_dir.mkdir()

        yield {
            "project_dir": project_dir,
            "content_dir": content_dir,
            "templates_dir": templates_dir,
            "output_dir": output_dir,
        }


@pytest.fixture
def config_with_templates(temp_project_dir):
    """Create a config with template configuration."""
    dirs = temp_project_dir

    template_config = TemplateConfig(
        template_path=dirs["templates_dir"],
        base_templates=["home.html"],
        note_templates=[],
    )

    return ScribeConfig(
        source_dir=dirs["content_dir"],
        output_dir=dirs["output_dir"],
        templates=template_config,
        site_title="Test Site",
        site_description="A test site",
        site_url="https://example.com",
    )


class TestTemplateContext:
    """Test template context generation and availability."""

    def test_global_context_contains_build_metadata(self, config_with_templates):
        """Test that global context includes build_metadata."""
        builder = SiteBuilder(config_with_templates)
        context = builder._create_global_context()

        # Check that build_metadata exists
        assert "build_metadata" in context

        # Check build_metadata structure
        build_metadata = context["build_metadata"]
        assert "generator" in build_metadata
        assert "version" in build_metadata
        assert "build_time" in build_metadata

        # Check values
        assert build_metadata["generator"] == "Scribe"
        assert build_metadata["version"] == "1.0.0"
        assert build_metadata["build_time"] is not None

        # Check build_time is a valid ISO format datetime
        build_time = build_metadata["build_time"]
        assert isinstance(build_time, str)
        # Should be able to parse as datetime
        datetime.fromisoformat(build_time)

    def test_global_context_contains_site_metadata(self, config_with_templates):
        """Test that global context includes site metadata."""
        builder = SiteBuilder(config_with_templates)
        context = builder._create_global_context()

        # Check site metadata
        assert "site" in context
        site = context["site"]
        assert site["title"] == "Test Site"
        assert site["description"] == "A test site"
        assert site["url"] == "https://example.com"

    def test_global_context_contains_config(self, config_with_templates):
        """Test that global context includes config."""
        builder = SiteBuilder(config_with_templates)
        context = builder._create_global_context()

        # Check config is present
        assert "config" in context
        config_dict = context["config"]
        assert isinstance(config_dict, dict)
        assert "site_title" in config_dict
        assert config_dict["site_title"] == "Test Site"

    @pytest.mark.asyncio
    async def test_base_template_rendering_with_build_metadata(
        self, config_with_templates, temp_project_dir
    ):
        """Test that base templates can access build_metadata without errors."""
        dirs = temp_project_dir

        # Create a template that uses build_metadata
        template_content = """<!DOCTYPE html>
<html>
<head>
    <title>{{ site.title }}</title>
    <meta name="generator"
          content="{{ build_metadata.generator }} {{ build_metadata.version }}">
</head>
<body>
    <h1>{{ site.title }}</h1>
    <p>Built at: {{ build_metadata.build_time }}</p>
</body>
</html>"""

        template_file = dirs["templates_dir"] / "home.html"
        template_file.write_text(template_content)

        # Build the site
        builder = SiteBuilder(config_with_templates)
        await builder._build_base_templates()

        # Check output file was created
        output_file = dirs["output_dir"] / "home.html"
        assert output_file.exists()

        # Check content includes build metadata
        content = output_file.read_text()
        assert "Scribe 1.0.0" in content
        assert "Built at:" in content
        assert "Test Site" in content

    @pytest.mark.asyncio
    async def test_base_template_error_handling(
        self, config_with_templates, temp_project_dir
    ):
        """Test that template errors are handled gracefully."""
        dirs = temp_project_dir

        # Create a template with undefined variable
        template_content = """<!DOCTYPE html>
<html>
<head>
    <title>{{ undefined_variable }}</title>
</head>
<body>
    <h1>This should fail</h1>
</body>
</html>"""

        template_file = dirs["templates_dir"] / "home.html"
        template_file.write_text(template_content)

        # Build should not crash but handle the error
        builder = SiteBuilder(config_with_templates)
        # Should not raise an exception
        await builder._build_base_templates()

        # Check that error was handled gracefully
        # The important thing is no exception was raised

    def test_global_context_contains_notes_accessor(self, config_with_templates):
        """Test that global context includes notes accessor."""
        builder = SiteBuilder(config_with_templates)
        context = builder._create_global_context()

        # Check notes accessor is present
        assert "notes" in context
        from scribe.builder import NotesAccessor

        assert isinstance(context["notes"], NotesAccessor)

    @pytest.mark.asyncio
    async def test_notes_accessor_functionality(
        self, config_with_templates, temp_project_dir
    ):
        """Test that notes accessor can filter and return notes."""
        dirs = temp_project_dir

        # Create test markdown files
        note1_content = """---
title: Published Note
tags: [python, tutorial]
status: publish
---
# Published Note
This is a published note."""

        note2_content = """---
title: Draft Note
tags: [javascript]
status: draft
---
# Draft Note
This is a draft note."""

        (dirs["content_dir"] / "note1.md").write_text(note1_content)
        (dirs["content_dir"] / "note2.md").write_text(note2_content)

        # Build the site to populate processed_notes
        builder = SiteBuilder(config_with_templates)
        await builder.build_site()

        # Test notes accessor
        context = builder._create_global_context()
        notes_accessor = context["notes"]

        # Test all() method
        all_notes = notes_accessor.all()
        assert len(all_notes) == 2  # Should have both notes

        # Test filter() method
        published_notes = notes_accessor.filter("is_published")
        assert len(published_notes) == 1  # Should have one published note

        draft_notes = notes_accessor.filter("is_draft")
        assert len(draft_notes) == 1  # Should have one draft note

        # Check that filtered notes have correct structure
        if published_notes:
            note = published_notes[0]
            assert "title" in note
            assert "content" in note
            assert "tags" in note
            assert "status" in note
