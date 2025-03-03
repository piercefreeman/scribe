from re import DOTALL, finditer, sub
from typing import Set, Tuple


class MarkdownParser:
    """Helper class for parsing markdown content, specifically focused on extracting links and images."""

    @staticmethod
    def find_markdown_links(text: str) -> list[Tuple[str, str]]:
        """
        Find all markdown links in the text that haven't been escaped.
        Returns a list of tuples (text, url). Excludes image links.
        """
        matches = finditer(r"[^!\\]\[(.*?)\]\((.+?)\)", text)
        return [(match.group(1), match.group(2)) for match in matches]

    @staticmethod
    def find_markdown_images(text: str) -> list[Tuple[str, str]]:
        """
        Find all markdown image links in the text.
        Returns a list of tuples (alt_text, url).
        """
        # Look for image syntax that isn't escaped with a backslash
        matches = finditer(r"(?<!\\)!\[(.*?)\]\((.+?)\)", text)
        return [(match.group(1), match.group(2)) for match in matches]

    @staticmethod
    def find_html_images(text: str) -> list[str]:
        """
        Find all HTML image tags in the text and extract their src attributes.
        Returns a list of image URLs.
        """
        # More strict HTML img tag pattern that requires proper attribute syntax
        matches = finditer(r"<img\s+[^>]*?src=[\"']([^\"']+)[\"'][^>]*/?>", text)
        return [match.group(1) for match in matches]

    @staticmethod
    def is_external_url(url: str) -> bool:
        """Check if a URL is external (starts with http://, https://, or www.)"""
        return any(url.startswith(prefix) for prefix in ["http://", "https://", "www."])

    @staticmethod
    def extract_referenced_images(text: str) -> Set[str]:
        """
        Find all image paths referenced in the text, either through markdown
        or HTML img tags. Returns normalized filenames.
        """
        parser = MarkdownParser()
        image_paths = set()

        # Extract paths from markdown matches
        for _, path in parser.find_markdown_images(text):
            image_paths.add(path)

        # Extract paths from HTML matches
        for path in parser.find_html_images(text):
            image_paths.add(path)

        return image_paths

    @staticmethod
    def extract_external_urls(text: str) -> Set[str]:
        """
        Extract all external URLs from markdown content.
        """
        parser = MarkdownParser()
        urls = set()

        # Find markdown links that haven't been escaped
        for _, url in parser.find_markdown_links(text):
            if parser.is_external_url(url):
                # Remove escape characters
                clean_url = sub(r"\\(.)", r"\1", url)
                urls.add(clean_url)

        return urls

    @staticmethod
    def find_footnote_references(text: str) -> list[str]:
        """
        Find all footnote references in the text (e.g., [^1], [^note]).
        Returns a list of footnote identifiers.
        """
        matches = finditer(r"\[\^([\w-]+)\](?!\:)", text)
        return [match.group(1) for match in matches]

    @staticmethod
    def find_footnote_definitions(text: str) -> list[Tuple[str, str]]:
        """
        Find all footnote definitions in the text (e.g., [^1]: Some text).
        Returns a list of tuples (identifier, content).
        """
        matches = finditer(r"\[\^([\w-]+)\]\:(.*?)(?=\n\[|\n\n|$)", text, flags=DOTALL)
        return [(match.group(1), match.group(2).strip()) for match in matches]

    @staticmethod
    def has_footnotes(text: str) -> bool:
        """
        Check if the text contains any footnotes (either references or definitions).
        More robust than just checking for [^ as it ensures the footnote syntax is valid.
        """
        # First check for any footnote references
        if len(MarkdownParser.find_footnote_references(text)) > 0:
            return True

        # Then check for any footnote definitions
        if len(MarkdownParser.find_footnote_definitions(text)) > 0:
            return True

        return False
