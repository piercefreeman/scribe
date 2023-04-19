from dataclasses import dataclass

from scribe.note import Note


@dataclass
class PageDirection:
    """
    Indicates that a page has additional content on a subsequent page

    """
    direction: str
    index: int

@dataclass
class TemplateArguments:
    """
    All arguments that can be passed to a template are wrapped here, to provide
    common type-checking while allowing us to differently parameterize each of the
    page definitions with separate attributes.

    """
    offset: int | None = None
    limit: int | None = None
    notes: list[Note] | None = None

    directions: list[PageDirection] | None = None


@dataclass
class PageDefinition:
    template: str
    url: str
    page_args: TemplateArguments | None = None
