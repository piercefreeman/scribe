from dataclasses import dataclass
from datetime import datetime
from re import findall, sub
from typing import Any

from bs4 import BeautifulSoup
from markdown import markdown
from pydantic import ValidationError
from yaml import safe_load as yaml_loads

from scribe.metadata import NoteMetadata


class InvalidMetadataException(Exception):
    def __init__(self, message):
        self.message = message


@dataclass
class ParsedPayload:
    """
    Defines a value payload that has been successfully parsed by lexers

    """

    result: Any
    parsed_lines: list[int]


@dataclass
class ParsedText(ParsedPayload):
    result: str


@dataclass
class ParsedMetadata(ParsedPayload):
    result: NoteMetadata


def parse_title(text: str) -> ParsedText:
    """
    Determine if the first line is a header

    """
    first_line = text.strip().split("\n")[0]
    headers = findall(r"(#+)(.*)", first_line)
    headers = sorted(headers, key=lambda x: len(x[0]))
    if not headers:
        raise InvalidMetadataException("No header specified.")
    return ParsedText(result=headers[0][1].strip(), parsed_lines=[0])


def parse_metadata(text: str) -> ParsedMetadata:
    metadata_string = ""
    meta_started = False
    parsed_lines = []
    for i, line in enumerate(text.split("\n")):
        # Start read with the meta: tag indication that we have
        # started to declare the dictionary, end it otherwise.
        if line.strip() == "meta:":
            meta_started = True
        if line.strip() == "":
            meta_started = False
        if meta_started:
            metadata_string += f"{line}\n"
            parsed_lines.append(i)

    if not metadata_string:
        # If users haven't specified metadata, assume it is a scratch note
        return ParsedMetadata(result=NoteMetadata(date=datetime.now()), parsed_lines=[])

    try:
        metadata = NoteMetadata.parse_obj(yaml_loads(metadata_string)["meta"])
    except ValidationError as e:
        raise InvalidMetadataException(str(e))

    return ParsedMetadata(result=metadata, parsed_lines=parsed_lines)


def get_raw_text(text, parsed_payloads: list[ParsedPayload]) -> str:
    ignore_lines = {line for parsed in parsed_payloads for line in parsed.parsed_lines}

    text = "\n".join(
        [line for i, line in enumerate(text.split("\n")) if i not in ignore_lines]
    ).strip()

    # Normalize image patterns to ![]()
    # Different markdown implementations have different patterns for this
    text = sub(r"!\[\[(.*)\]\]", r"![](\1)", text)

    return text


def get_simple_content(text: str):
    html = markdown(text.split("\n")[0])
    content = "".join(BeautifulSoup(html, "html.parser").findAll(text=True))
    return sub(r"\s", " ", content)
