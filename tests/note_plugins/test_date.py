"""Tests for the date plugin."""

from datetime import datetime
from pathlib import Path

import pytest

from scribe.context import PageContext
from scribe.note_plugins.config import DatePluginConfig
from scribe.note_plugins.date import DatePlugin


class TestDatePlugin:
    """Test cases for the DatePlugin."""

    @pytest.fixture
    def plugin(self):
        """Create a DatePlugin instance for testing."""
        config = DatePluginConfig()
        return DatePlugin(config)

    @pytest.fixture
    def base_context(self):
        """Create a base PageContext for testing."""
        return PageContext(
            source_path=Path("test.md"),
            relative_path=Path("test.md"),
            output_path=Path("test.html"),
            raw_content="",
            content="",
        )

    @pytest.mark.parametrize(
        "date_str,expected_parsed",
        [
            ("2025-03-06", datetime(2025, 3, 6)),
            ("2025-03-06 14:30:00", datetime(2025, 3, 6, 14, 30, 0)),
            ("2025/03/06", datetime(2025, 3, 6)),
            ("March 6, 2025", datetime(2025, 3, 6)),
            ("Mar 6, 2025", datetime(2025, 3, 6)),
            ("December 31, 2024", datetime(2024, 12, 31)),
            ("Jan 1, 2025", datetime(2025, 1, 1)),
        ],
    )
    async def test_valid_date_formats(
        self, plugin, base_context, date_str, expected_parsed
    ):
        """Test that various valid date formats are parsed correctly."""
        context = base_context
        context.date = date_str

        result = await plugin.process(context)

        assert result.date == date_str
        assert result.date_data is not None
        assert result.date_data.raw == date_str
        assert result.date_data.parsed == expected_parsed
        assert result.date_data.formatted == expected_parsed.strftime("%B %d, %Y")
        assert result.date_data.iso == expected_parsed.isoformat()

    @pytest.mark.parametrize(
        "invalid_date",
        [
            "invalid-date",
            "2025-13-01",  # Invalid month
            "2025-02-30",  # Invalid day
            "March 32, 2025",  # Invalid day
            "Marcha 6, 2025",  # Invalid month name
            "2025/13/01",  # Invalid month in slash format
            "",  # Empty string
            "not a date at all",
        ],
    )
    async def test_invalid_date_formats(
        self, plugin, base_context, invalid_date, capsys
    ):
        """Test that invalid date formats log errors and don't crash."""
        context = base_context
        context.date = invalid_date

        result = await plugin.process(context)

        # Date should remain unchanged
        assert result.date == invalid_date
        # No plugin data should be set
        assert result.date_data is None

    async def test_no_date_in_context(self, plugin, base_context):
        """Test that plugin handles context with no date gracefully."""
        context = base_context
        context.date = None

        result = await plugin.process(context)

        assert result.date is None
        assert result.date_data is None

    async def test_non_string_date(self, plugin, base_context):
        """Test that plugin handles non-string date values gracefully."""
        context = base_context
        context.date = 123  # Non-string date

        result = await plugin.process(context)

        assert result.date == 123
        assert result.date_data is None

    async def test_already_parsed_date(self, plugin, base_context):
        """Test that plugin handles already parsed datetime objects gracefully."""
        context = base_context
        context.date = datetime(2025, 3, 6)

        result = await plugin.process(context)

        assert result.date == datetime(2025, 3, 6)
        assert result.date_data is None
