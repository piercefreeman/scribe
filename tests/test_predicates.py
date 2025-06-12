"""Tests for predicate system in SiteBuilder."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from scribe.builder import SiteBuilder
from scribe.config import ScribeConfig, TemplateConfig
from scribe.context import PageContext, PageStatus


class TestPredicates:
    """Test cases for predicate system."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a basic config for testing."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()

        template_config = TemplateConfig(
            template_path=template_dir, base_templates=[], note_templates=[]
        )

        return ScribeConfig(
            source_dir=tmp_path / "content",
            output_dir=tmp_path / "output",
            templates=template_config,
        )

    @pytest.fixture
    def builder(self, config):
        """Create a SiteBuilder instance for testing."""
        return SiteBuilder(config)

    @pytest.fixture
    def page_context(self, tmp_path):
        """Create a basic page context for testing."""
        source_file = tmp_path / "test.md"
        source_file.touch()

        return PageContext(
            source_path=source_file,
            relative_path=Path("test.md"),
            output_path=tmp_path / "output" / "test.html",
            raw_content="# Test Content",
            modified_time=1234567890,
            config=Mock(),
        )

    def test_default_predicates_setup(self, builder):
        """Test that default predicates are properly set up."""
        predicates = builder.predicate_functions

        # Check all expected predicates exist
        assert "all" in predicates
        assert "has_tag" in predicates
        assert "is_published" in predicates
        assert "is_draft" in predicates
        assert "is_scratch" in predicates

    def test_all_predicate(self, builder, page_context):
        """Test the 'all' predicate always returns True."""
        predicate_func = builder.predicate_functions["all"]
        assert predicate_func(page_context) is True

    def test_is_published_predicate(self, builder, page_context):
        """Test the 'is_published' predicate."""
        predicate_func = builder.predicate_functions["is_published"]

        # Published note
        page_context.status = PageStatus.PUBLISH
        assert predicate_func(page_context) is True

        # Draft note
        page_context.status = PageStatus.DRAFT
        assert predicate_func(page_context) is False

        # Scratch note
        page_context.status = PageStatus.SCRATCH
        assert predicate_func(page_context) is False

    def test_is_draft_predicate(self, builder, page_context):
        """Test the 'is_draft' predicate."""
        predicate_func = builder.predicate_functions["is_draft"]

        # Draft note
        page_context.status = PageStatus.DRAFT
        assert predicate_func(page_context) is True

        # Published note
        page_context.status = PageStatus.PUBLISH
        assert predicate_func(page_context) is False

        # Scratch note
        page_context.status = PageStatus.SCRATCH
        assert predicate_func(page_context) is False

    def test_is_scratch_predicate(self, builder, page_context):
        """Test the 'is_scratch' predicate."""
        predicate_func = builder.predicate_functions["is_scratch"]

        # Scratch note
        page_context.status = PageStatus.SCRATCH
        assert predicate_func(page_context) is True

        # Published note
        page_context.status = PageStatus.PUBLISH
        assert predicate_func(page_context) is False

        # Draft note
        page_context.status = PageStatus.DRAFT
        assert predicate_func(page_context) is False

    def test_has_tag_predicate(self, builder, page_context):
        """Test the 'has_tag' predicate with different tag scenarios."""
        has_tag_factory = builder.predicate_functions["has_tag"]

        # Test with no tags
        page_context.tags = None
        has_python = has_tag_factory("python")
        assert has_python(page_context) is False

        # Test with empty tags list
        page_context.tags = []
        assert has_python(page_context) is False

        # Test with tags that don't include the target
        page_context.tags = ["javascript", "web"]
        assert has_python(page_context) is False

        # Test with tags that include the target
        page_context.tags = ["python", "tutorial"]
        assert has_python(page_context) is True

        # Test case sensitivity
        page_context.tags = ["Python"]
        assert has_python(page_context) is False  # Case sensitive

        # Test exact match
        has_web = has_tag_factory("web")
        page_context.tags = ["web", "python"]
        assert has_web(page_context) is True

    def test_note_matches_template_no_predicates(self, builder, page_context):
        """Test that notes match templates with no predicates."""
        note_template = Mock()
        note_template.predicates = []

        assert builder._note_matches_template(page_context, note_template) is True

    def test_note_matches_template_single_predicate(self, builder, page_context):
        """Test note matching with a single predicate."""
        note_template = Mock()
        note_template.predicates = ["is_published"]

        # Published note should match
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Draft note should not match
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False

    def test_note_matches_template_multiple_predicates(self, builder, page_context):
        """Test note matching with multiple predicates (AND logic)."""
        note_template = Mock()
        note_template.predicates = ["is_published", "all"]

        # Both predicates should pass
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # One predicate fails
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False

    def test_note_matches_template_with_has_tag(self, builder, page_context):
        """Test note matching with has_tag predicate."""
        # Note: has_tag is a factory function, need to register actual function
        builder.predicate_functions["has_python"] = builder.predicate_functions[
            "has_tag"
        ]("python")

        note_template = Mock()
        note_template.predicates = ["has_python"]

        # Note with python tag should match
        page_context.tags = ["python", "tutorial"]
        assert builder._note_matches_template(page_context, note_template) is True

        # Note without python tag should not match
        page_context.tags = ["javascript", "web"]
        assert builder._note_matches_template(page_context, note_template) is False

    def test_negation_single_predicate(self, builder, page_context):
        """Test negation with exclamation point prefix."""
        note_template = Mock()
        note_template.predicates = ["!is_draft"]

        # Published note should match !is_draft
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Draft note should not match !is_draft
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False

    def test_negation_multiple_predicates(self, builder, page_context):
        """Test negation with multiple predicates."""
        note_template = Mock()
        note_template.predicates = ["!is_draft", "all"]

        # Published note should match both !is_draft and all
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Draft note should not match !is_draft
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False

    def test_negation_with_has_tag(self, builder, page_context):
        """Test negation with has_tag predicate."""
        # Register a specific has_tag function for testing
        builder.predicate_functions["has_python"] = builder.predicate_functions[
            "has_tag"
        ]("python")

        note_template = Mock()
        note_template.predicates = ["!has_python"]

        # Note without python tag should match !has_python
        page_context.tags = ["javascript", "web"]
        assert builder._note_matches_template(page_context, note_template) is True

        # Note with python tag should not match !has_python
        page_context.tags = ["python", "tutorial"]
        assert builder._note_matches_template(page_context, note_template) is False

    def test_mixed_positive_and_negative_predicates(self, builder, page_context):
        """Test mixing positive and negative predicates."""
        # Register specific has_tag functions
        builder.predicate_functions["has_python"] = builder.predicate_functions[
            "has_tag"
        ]("python")
        builder.predicate_functions["has_draft"] = builder.predicate_functions[
            "has_tag"
        ]("draft")

        note_template = Mock()
        note_template.predicates = ["has_python", "!has_draft", "!is_draft"]

        # Note should have python tag, not have draft tag, and not be a draft
        page_context.tags = ["python", "tutorial"]
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Fail because it has draft tag
        page_context.tags = ["python", "draft"]
        assert builder._note_matches_template(page_context, note_template) is False

        # Fail because it's a draft
        page_context.tags = ["python", "tutorial"]
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False

        # Fail because it doesn't have python tag
        page_context.tags = ["javascript", "tutorial"]
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is False

    def test_unknown_predicate_handling(self, builder, page_context, capsys):
        """Test handling of unknown predicates."""
        note_template = Mock()
        note_template.predicates = ["unknown_predicate"]

        # Should return False and print warning
        assert builder._note_matches_template(page_context, note_template) is False

        # Check that warning was printed (we can't easily test rich console output,
        # but we can test the logic)

    def test_unknown_predicate_with_negation(self, builder, page_context):
        """Test handling of unknown predicates with negation."""
        note_template = Mock()
        note_template.predicates = ["!unknown_predicate"]

        # Should return False for unknown predicate even with negation
        assert builder._note_matches_template(page_context, note_template) is False

    def test_edge_case_empty_predicate_list(self, builder, page_context):
        """Test edge case with empty predicate list."""
        note_template = Mock()
        note_template.predicates = []

        # Empty predicate list should match all notes
        assert builder._note_matches_template(page_context, note_template) is True

    def test_edge_case_none_predicates(self, builder, page_context):
        """Test edge case with None predicates."""
        note_template = Mock()
        note_template.predicates = None

        # None predicates should match all notes
        assert builder._note_matches_template(page_context, note_template) is True

    def test_complex_predicate_combinations(self, builder, page_context):
        """Test complex combinations of predicates."""
        # Register multiple has_tag functions
        builder.predicate_functions["has_python"] = builder.predicate_functions[
            "has_tag"
        ]("python")
        builder.predicate_functions["has_tutorial"] = builder.predicate_functions[
            "has_tag"
        ]("tutorial")
        builder.predicate_functions["has_advanced"] = builder.predicate_functions[
            "has_tag"
        ]("advanced")

        note_template = Mock()
        note_template.predicates = [
            "has_python",
            "has_tutorial",
            "!has_advanced",
            "!is_draft",
        ]

        # Should match: python tutorial that's not advanced and not a draft
        page_context.tags = ["python", "tutorial", "beginner"]
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Should not match: has advanced tag
        page_context.tags = ["python", "tutorial", "advanced"]
        assert builder._note_matches_template(page_context, note_template) is False

        # Should not match: is draft
        page_context.tags = ["python", "tutorial", "beginner"]
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False

        # Should not match: missing tutorial tag
        page_context.tags = ["python", "beginner"]
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is False

    def test_has_tag_colon_syntax(self, builder, page_context):
        """Test has_tag:tagname syntax."""
        note_template = Mock()
        note_template.predicates = ["has_tag:travel", "is_published"]

        # Should match: note with travel tag and published status
        page_context.tags = ["travel", "vacation"]
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Should not match: missing travel tag
        page_context.tags = ["vacation", "fun"]
        assert builder._note_matches_template(page_context, note_template) is False

        # Should not match: not published
        page_context.tags = ["travel", "vacation"]
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False

    def test_has_tag_colon_syntax_with_negation(self, builder, page_context):
        """Test has_tag:tagname syntax with negation."""
        note_template = Mock()
        note_template.predicates = ["!has_tag:work", "is_published"]

        # Should match: note without work tag and published
        page_context.tags = ["travel", "vacation"]
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Should not match: has work tag
        page_context.tags = ["work", "meeting"]
        assert builder._note_matches_template(page_context, note_template) is False

    def test_generic_parameterized_predicates(self, builder, page_context):
        """Test generic parameterized predicate system with has_tag."""
        note_template = Mock()
        note_template.predicates = ["has_tag:python", "has_tag:tutorial"]

        # Should match: has both tags
        page_context.tags = ["python", "tutorial", "beginner"]
        assert builder._note_matches_template(page_context, note_template) is True

        # Should not match: missing python tag
        page_context.tags = ["tutorial", "beginner"]
        assert builder._note_matches_template(page_context, note_template) is False

        # Should not match: missing tutorial tag
        page_context.tags = ["python", "beginner"]
        assert builder._note_matches_template(page_context, note_template) is False

    def test_parameterized_predicates_with_negation(self, builder, page_context):
        """Test parameterized predicates with negation."""
        note_template = Mock()
        note_template.predicates = ["!has_tag:draft", "!has_tag:admin"]

        # Should match: doesn't have either tag
        page_context.tags = ["python", "tutorial"]
        assert builder._note_matches_template(page_context, note_template) is True

        # Should not match: has draft tag
        page_context.tags = ["python", "draft"]
        assert builder._note_matches_template(page_context, note_template) is False

        # Should not match: has admin tag
        page_context.tags = ["python", "admin"]
        assert builder._note_matches_template(page_context, note_template) is False

    def test_non_parameterized_predicate_with_colon_fails(self, builder, page_context):
        """Test that non-parameterized predicates with colon syntax fail gracefully."""
        note_template = Mock()
        note_template.predicates = ["is_published:something"]

        # Should fail because is_published doesn't accept parameters
        assert builder._note_matches_template(page_context, note_template) is False

    def test_unknown_parameterized_predicate(self, builder, page_context):
        """Test unknown parameterized predicates."""
        note_template = Mock()
        note_template.predicates = ["unknown_predicate:param"]

        # Should fail because unknown_predicate doesn't exist
        assert builder._note_matches_template(page_context, note_template) is False

    def test_mixed_parameterized_and_regular_predicates(self, builder, page_context):
        """Test mixing parameterized and regular predicates."""
        note_template = Mock()
        note_template.predicates = [
            "has_tag:python",
            "is_published",
            "has_tag:tutorial",
        ]

        # Should match all conditions
        page_context.tags = ["python", "tutorial"]
        page_context.status = PageStatus.PUBLISH
        assert builder._note_matches_template(page_context, note_template) is True

        # Should not match: missing python tag
        page_context.tags = ["tutorial"]
        assert builder._note_matches_template(page_context, note_template) is False

        # Should not match: not published
        page_context.tags = ["python", "tutorial"]
        page_context.status = PageStatus.DRAFT
        assert builder._note_matches_template(page_context, note_template) is False
