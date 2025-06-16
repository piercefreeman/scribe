"""Tests for builder functionality."""

from pathlib import Path

import pytest

from scribe.builder import _get_output_path_from_input_path


class TestOutputPathTransformation:
    """Test cases for output path transformation logic for regular pages/templates."""

    @pytest.mark.parametrize(
        "input_path,expected_output",
        [
            # Markdown files become HTML
            ("post.md", "post.html"),
            ("blog/article.md", "blog/article.html"),
            ("nested/deep/content.markdown", "nested/deep/content.html"),
            # Jinja template files become HTML
            ("template.j2", "template.html"),
            ("layout.jinja", "layout.html"),
            ("base.jinja2", "base.html"),
            # Compound jinja suffixes are stripped properly
            ("index.html.j2", "index.html"),
            ("style.css.jinja", "style.css"),
            ("config.json.jinja2", "config.json"),
            # Other files mirror their input
            ("style.css", "style.css"),
            ("script.js", "script.js"),
            ("image.png", "image.png"),
            ("data.json", "data.json"),
            ("README", "README"),
            # Complex nested paths
            ("assets/styles/main.css", "assets/styles/main.css"),
            ("templates/partials/header.j2", "templates/partials/header.html"),
            ("content/blog/2023/post.md", "content/blog/2023/post.html"),
        ],
    )
    def test_get_output_path_from_input_path(
        self, input_path: str, expected_output: str
    ):
        """Test output path transformation for various input paths."""
        input_path_obj = Path(input_path)
        expected_path_obj = Path(expected_output)

        result = _get_output_path_from_input_path(input_path_obj)

        assert result == expected_path_obj

        # Ensure result is a Path object
        assert isinstance(result, Path)

    def test_get_output_path_preserves_directory_structure(self):
        """Test that directory structure is preserved in output path."""
        input_path = Path("deep/nested/directory/structure/file.md")
        result = _get_output_path_from_input_path(input_path)

        expected = Path("deep/nested/directory/structure/file.html")
        assert result == expected
        assert result.parent == expected.parent

    def test_get_output_path_handles_empty_extensions(self):
        """Test handling of files without extensions."""
        input_path = Path("Makefile")
        result = _get_output_path_from_input_path(input_path)

        assert result == Path("Makefile")

    def test_get_output_path_case_sensitivity(self):
        """Test that file extensions are handled with proper case sensitivity."""
        # Extensions should be matched exactly (case-sensitive)
        input_path = Path("template.J2")  # Uppercase
        result = _get_output_path_from_input_path(input_path)

        # Should not be transformed since .J2 != .j2
        assert result == Path("template.J2")

    def test_get_output_path_multiple_dots(self):
        """Test handling of files with multiple dots in filename."""
        input_path = Path("my.config.file.j2")
        result = _get_output_path_from_input_path(input_path)

        assert result == Path("my.config.file.html")
