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
        Also ensures footnote definitions are arranged in numerical order.

        Args:
            text: The markdown text to reorder footnotes in

        Returns:
            Text with reordered footnotes and definitions
        """
        references = cls.find_references(text)
        definitions = cls.find_definitions(text)

        if not references or not definitions:
            return text

        number_map = cls.create_renumbering_map(references)
        # Create reverse mapping for definition ordering
        reverse_map = {new: old for old, new in number_map.items()}

        # Create a list of all replacements to make for references
        replacements = []
        for old_num, new_num in number_map.items():
            # Add reference replacements (not definitions)
            replacements.extend(
                [
                    (match.start(), match.end(), f"[^{new_num}]")
                    for match in re.finditer(f"\\[\\^{old_num}\\](?!:)", text)
                ]
            )

        # Sort replacements by position in reverse order to maintain string indices
        replacements.sort(key=lambda x: x[0], reverse=True)

        # Apply reference replacements from end to start to avoid index shifting
        result = text
        for start, end, replacement in replacements:
            result = result[:start] + replacement + result[end:]

        # Now handle reordering the definitions
        # First, create a mapping of old numbers to their content and indentation
        definition_map = {}
        lines = result.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            match = re.match(r"^(\s*)\[\^(\d+)\]:\s*(.*)$", line)
            if match:
                indent, num, content = match.groups()
                multiline_content = [content]
                i += 1
                # Collect any continuation lines
                while i < len(lines):
                    next_line = lines[i]
                    if not next_line.strip() or re.match(r"^\s*\[\^", next_line):
                        break
                    # Preserve the content without the leading spaces
                    multiline_content.append(next_line.strip())
                    i += 1
                definition_map[num] = {"content": "\n".join(multiline_content), "indent": indent}
                continue
            i += 1

        # Find the start of the definitions section
        definitions_start = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*\[\^", line):
                definitions_start = i
                break

        if definitions_start is not None:
            # Create new ordered definitions
            new_definitions = []
            base_indent = definition_map[next(iter(definition_map))]["indent"]

            # Sort by new number to maintain numerical order
            for new_num in sorted(
                (
                    num
                    for old_num in definition_map.keys()
                    if old_num in number_map
                    for num in [number_map[old_num]]
                ),
                key=int,
            ):
                old_num = reverse_map[new_num]
                if old_num in definition_map:
                    def_info = definition_map[old_num]
                    content_lines = def_info["content"].split("\n")
                    # First line with footnote marker
                    new_definitions.append(f"{base_indent}[^{new_num}]: {content_lines[0]}")
                    # Continuation lines
                    for cont_line in content_lines[1:]:
                        new_definitions.append(f"{base_indent}{cont_line}")

            # Replace the old definitions section
            while definitions_start < len(lines):
                if not lines[definitions_start].strip():
                    break
                lines[definitions_start] = ""
                definitions_start += 1

            # Insert new definitions
            lines[definitions_start - len(new_definitions) : definitions_start] = new_definitions

        return "\n".join(lines)

    @classmethod
    def has_footnotes(cls, text: str) -> bool:
        """Check if the text contains any footnotes.

        Args:
            text: The markdown text to check

        Returns:
            True if the text contains footnotes, False otherwise
        """
        return "[^" in text
