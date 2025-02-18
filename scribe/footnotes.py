import re
from typing import Dict, List, Tuple


class FootnoteParser:
    """Parser for handling markdown footnotes and their reordering."""

    REFERENCE_PATTERN = r"\[\^(\d+)\]"
    DEFINITION_PATTERN = r"\[\^(\d+)\]:\s*((?:[^\n][\n]?(?![\n]|\[\^\d+\]:))*)"

    @classmethod
    def find_references(cls, text: str) -> List[Tuple[str, int]]:
        """Find all footnote references in the text and their positions.
        Returns a list of tuples (footnote_id, position).

        Args:
            text: The markdown text to parse

        Returns:
            List of tuples containing (footnote_id, position)
        """
        return [
            (match.group(1), match.start()) for match in re.finditer(cls.REFERENCE_PATTERN, text)
        ]

    @classmethod
    def find_definitions(cls, text: str) -> List[Tuple[str, str, int]]:
        """Find all footnote definitions in the text.
        Returns a list of tuples (footnote_id, content, position).

        Args:
            text: The markdown text to parse

        Returns:
            List of tuples containing (footnote_id, content, position)
        """
        matches = re.finditer(cls.DEFINITION_PATTERN, text)
        return [(match.group(1), match.group(2).strip(), match.start()) for match in matches]

    @classmethod
    def create_renumbering_map(cls, references: List[Tuple[str, int]]) -> Dict[str, str]:
        """Create a mapping of old footnote numbers to new sequential numbers.

        Args:
            references: List of tuples containing (footnote_id, position)

        Returns:
            Dictionary mapping old footnote numbers to new sequential numbers
        """
        sorted_refs = sorted(references, key=lambda x: x[1])
        return {old_num: str(i + 1) for i, (old_num, _) in enumerate(sorted_refs)}

    @classmethod
    def reorder(cls, text: str) -> str:
        """Reorder footnotes in the text to be sequential based on appearance.

        Args:
            text: The markdown text to reorder footnotes in

        Returns:
            Text with reordered footnotes
        """
        references = cls.find_references(text)
        definitions = cls.find_definitions(text)

        if not references or not definitions:
            return text

        number_map = cls.create_renumbering_map(references)

        # Replace references and definitions, starting with longest numbers first
        # to avoid partial replacements
        for old_num in sorted(number_map.keys(), key=len, reverse=True):
            new_num = number_map[old_num]
            text = re.sub(f"\\[\\^{old_num}\\](?!:)", f"[^{new_num}]", text)
            text = re.sub(f"\\[\\^{old_num}\\]:", f"[^{new_num}]:", text)

        return text

    @classmethod
    def has_footnotes(cls, text: str) -> bool:
        """Check if the text contains any footnotes.

        Args:
            text: The markdown text to check

        Returns:
            True if the text contains footnotes, False otherwise
        """
        return "[^" in text
