"""Date plugin for parsing and formatting dates in page metadata."""

from datetime import datetime

from rich.console import Console

from scribe.context import DateData, PageContext
from scribe.note_plugins.base import NotePlugin
from scribe.note_plugins.config import DatePluginConfig, PluginName

console = Console()


class DatePlugin(NotePlugin[DatePluginConfig]):
    """Plugin to handle date parsing and formatting."""

    name = PluginName.DATE

    async def process(self, ctx: PageContext) -> PageContext:
        """Parse and format dates."""
        if not ctx.date:
            return ctx

        if ctx.date and isinstance(ctx.date, str):
            # Try to parse common date formats
            formats = [
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d",
                "%B %d, %Y",  # March 6, 2025
                "%b %d, %Y",  # Mar 6, 2025
            ]

            parsed_successfully = False
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(ctx.date, fmt)
                    ctx.date_data = DateData(
                        raw=ctx.date,
                        parsed=parsed_date,
                        formatted=parsed_date.strftime("%B %d, %Y"),
                        iso=parsed_date.isoformat(),
                    )
                    parsed_successfully = True
                    break
                except ValueError:
                    continue

            if not parsed_successfully:
                console.print(
                    f"[red]Error:[/red] Unable to parse date format: '{ctx.date}'. "
                    f"Supported formats: YYYY-MM-DD, YYYY-MM-DD HH:MM:SS, "
                    f"YYYY/MM/DD, 'Month DD, YYYY', 'Mon DD, YYYY'"
                )

        return ctx
