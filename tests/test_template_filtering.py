"""Tests for template-based output filtering."""

import pytest

from scribe.builder import SiteBuilder
from scribe.config import NoteTemplate, ScribeConfig, TemplateConfig


class TestTemplateFiltering:
    """Test that output is only generated for notes matching note_templates."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory structure."""
        content_dir = tmp_path / "content"
        output_dir = tmp_path / "output"
        template_dir = tmp_path / "templates"

        content_dir.mkdir()
        output_dir.mkdir()
        template_dir.mkdir()

        return {
            "content": content_dir,
            "output": output_dir,
            "templates": template_dir,
        }

    @pytest.fixture
    def config_with_templates(self, temp_dir):
        """Create config with note templates."""
        # Create basic templates
        (temp_dir["templates"] / "post.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>{{ note.title }}</title></head>
<body>
    <h1>{{ note.title }}</h1>
    <div>{{ note.content | safe }}</div>
</body>
</html>
        """)

        (temp_dir["templates"] / "post-travel.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>Travel: {{ note.title }}</title></head>
<body>
    <h1>Travel: {{ note.title }}</h1>
    <div>{{ note.content | safe }}</div>
</body>
</html>
        """)

        template_config = TemplateConfig(
            template_path=temp_dir["templates"],
            note_templates=[
                NoteTemplate(
                    template_path="post.html",
                    url_pattern="/notes/{slug}/",
                    predicates=["is_published", "!has_tag:travel"],
                ),
                NoteTemplate(
                    template_path="post-travel.html",
                    url_pattern="/travel/{slug}/",
                    predicates=["is_published", "has_tag:travel"],
                ),
            ],
        )

        return ScribeConfig(
            source_dir=temp_dir["content"],
            output_dir=temp_dir["output"],
            templates=template_config,
        )

    @pytest.mark.asyncio
    async def test_only_matching_notes_generate_output(
        self, temp_dir, config_with_templates
    ):
        """Test that only notes matching templates generate output files."""
        content_dir = temp_dir["content"]
        output_dir = temp_dir["output"]

        # Create test notes
        # This should match the first template (published, no travel tag)
        (content_dir / "tech-post.md").write_text("""---
title: "Tech Post"
status: publish
tags: ["technology", "programming"]
---

# Tech Post

This is a technology post.
""")

        # This should match the second template (published, has travel tag)
        (content_dir / "travel-post.md").write_text("""---
title: "Travel Post"
status: publish
tags: ["travel", "vacation"]
---

# Travel Post

This is a travel post.
""")

        # This should NOT match any template (not published)
        (content_dir / "draft-post.md").write_text("""---
title: "Draft Post"
status: draft
tags: ["technology"]
---

# Draft Post

This is a draft post.
""")

        # This should NOT match any template (scratch status)
        (content_dir / "scratch-post.md").write_text("""---
title: "Scratch Post"
status: scratch
tags: ["random"]
---

# Scratch Post

This is a scratch post.
""")

        # Build the site
        builder = SiteBuilder(config_with_templates)
        await builder.build_site()

        # Check which files were generated
        expected_files = [
            output_dir / "notes" / "tech-post" / "index.html",  # matches first template
            output_dir
            / "travel"
            / "travel-post"
            / "index.html",  # matches second template
        ]

        unexpected_files = [
            output_dir / "draft-post.html",  # draft, shouldn't be generated
            output_dir / "scratch-post.html",  # scratch, shouldn't be generated
        ]

        # Verify expected files exist
        for expected_file in expected_files:
            assert expected_file.exists(), (
                f"Expected output file not found: {expected_file}"
            )

        # Verify unexpected files don't exist
        for unexpected_file in unexpected_files:
            assert not unexpected_file.exists(), (
                f"Unexpected output file found: {unexpected_file}"
            )

        # Verify the content is correct
        tech_content = expected_files[0].read_text()
        assert "Tech Post" in tech_content
        assert "<h1>Tech Post</h1>" in tech_content

        travel_content = expected_files[1].read_text()
        assert "Travel: Travel Post" in travel_content
        assert "<h1>Travel: Travel Post</h1>" in travel_content

    @pytest.mark.asyncio
    async def test_no_templates_no_output(self, temp_dir):
        """Test that no output is generated when no templates are configured."""
        content_dir = temp_dir["content"]
        output_dir = temp_dir["output"]

        # Create config without templates
        config = ScribeConfig(source_dir=content_dir, output_dir=output_dir)

        # Create a test note
        (content_dir / "test-post.md").write_text("""---
title: "Test Post"
status: publish
---

# Test Post

This is a test post.
""")

        # Build the site
        builder = SiteBuilder(config)
        await builder.build_site()

        # Check that no HTML files were generated (except maybe from base templates)
        html_files = list(output_dir.rglob("*.html"))
        assert len(html_files) == 0, f"Unexpected HTML files generated: {html_files}"

    @pytest.mark.asyncio
    async def test_note_matches_multiple_templates_first_wins(
        self, temp_dir, config_with_templates
    ):
        """Test that when a note matches multiple templates, the first one wins."""
        content_dir = temp_dir["content"]
        output_dir = temp_dir["output"]

        # Update config to have overlapping templates
        config_with_templates.templates.note_templates = [
            NoteTemplate(
                template_path="post.html",
                url_pattern="/posts/{slug}/",
                predicates=["is_published"],  # Broad match
            ),
            NoteTemplate(
                template_path="post-travel.html",
                url_pattern="/travel/{slug}/",
                predicates=["is_published", "has_tag:travel"],  # More specific match
            ),
        ]

        # Create a note that matches both templates
        (content_dir / "travel-adventure.md").write_text("""---
title: "Travel Adventure"
status: publish
tags: ["travel", "adventure"]
---

# Travel Adventure

This is a travel adventure post.
""")

        # Build the site
        builder = SiteBuilder(config_with_templates)
        await builder.build_site()

        # The first template should win, so it should be in /posts/ not /travel/
        expected_file = output_dir / "posts" / "travel-adventure" / "index.html"
        unexpected_file = output_dir / "travel" / "travel-adventure" / "index.html"

        assert expected_file.exists(), (
            f"Expected output file not found: {expected_file}"
        )
        assert not unexpected_file.exists(), (
            f"Unexpected output file found: {unexpected_file}"
        )

        # Verify it used the first template (not the travel-specific one)
        content = expected_file.read_text()
        assert "<title>Travel Adventure</title>" in content  # Regular template
        assert (
            "<title>Travel: Travel Adventure</title>" not in content
        )  # Not travel template
