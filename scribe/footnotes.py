import re
from typing import Dict, List, Tuple


class FootnoteParser:
    """Parser for handling markdown footnotes and their reordering."""

    REFERENCE_PATTERN = r"\[\^(\d+)\]"
    DEFINITION_START_PATTERN = r"^\s*\[\^(\d+)\]:\s*(.*)$"

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
        definitions = []
        lines = text.split("\n")
        current_definition = None
        current_content = []
        current_position = 0
        line_position = 0

        for line in lines:
            match = re.match(cls.DEFINITION_START_PATTERN, line)
            if match:
                # If we were building a previous definition, save it
                if current_definition:
                    definitions.append(
                        (current_definition, "\n".join(current_content).strip(), current_position)
                    )
                # Start new definition
                current_definition = match.group(1)
                current_content = [match.group(2)]
                current_position = line_position
            elif current_definition and line.strip() and not re.match(r"^\s*\[\^", line):
                # Continue multi-line definition if line is not empty and not a new definition
                current_content.append(line.strip())

            line_position += len(line) + 1  # +1 for the newline

        # Add the last definition if there is one
        if current_definition:
            definitions.append(
                (current_definition, "\n".join(current_content).strip(), current_position)
            )

        return definitions

    @classmethod
    def create_renumbering_map(cls, references: List[Tuple[str, int]]) -> Dict[str, str]:
        """Create a mapping of old footnote numbers to new sequential numbers.

        Args:
            references: List of tuples containing (footnote_id, position)

        Returns:
            Dictionary mapping old footnote numbers to new sequential numbers
        """
        sorted_refs = sorted(references, key=lambda x: x[1])
        unique_refs = []
        seen = set()
        for ref in sorted_refs:
            if ref[0] not in seen:
                unique_refs.append(ref)
                seen.add(ref[0])
        return {old_num: str(i + 1) for i, (old_num, _) in enumerate(unique_refs)}

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

        # Create a list of all replacements to make
        replacements = []
        for old_num, new_num in number_map.items():
            # Add reference replacements (not definitions)
            replacements.extend(
                [
                    (match.start(), match.end(), f"[^{new_num}]")
                    for match in re.finditer(f"\\[\\^{old_num}\\](?!:)", text)
                ]
            )
            # Add definition replacements
            replacements.extend(
                [
                    (match.start(), match.end(), f"[^{new_num}]:")
                    for match in re.finditer(f"\\[\\^{old_num}\\]:", text)
                ]
            )

        # Sort replacements by position in reverse order to maintain string indices
        replacements.sort(key=lambda x: x[0], reverse=True)

        # Apply replacements from end to start to avoid index shifting
        result = text
        for start, end, replacement in replacements:
            result = result[:start] + replacement + result[end:]

        return result

    @classmethod
    def has_footnotes(cls, text: str) -> bool:
        """Check if the text contains any footnotes.

        Args:
            text: The markdown text to check

        Returns:
            True if the text contains footnotes, False otherwise
        """
        return "[^" in text
