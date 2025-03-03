from pathlib import Path
from re import sub

from rapidfuzz import process
from rich.console import Console

from scribe.logging import LOGGER
from scribe.markdown import MarkdownParser
from scribe.note import Note

console = Console()


def local_to_remote_links(
    note: Note,
    path_to_remote: dict[str, str],
) -> str:
    """
    Notes are specified with relative file locations to the local filepath, which is better supported
    by knowledge graph tools like Obsidian. This function sniffs for local links and attempts to convert
    them into their server side counterparts using the `path_to_remote` index.

    :param path_to_remote: Specify the mapping from the local path (without path prefix)
        and the remote location of the file.
    """
    LOGGER.info(f"Converting links for note: {note.title}")
    note_text = note.text
    parser = MarkdownParser()

    # Get all markdown links and HTML images
    markdown_links = parser.find_markdown_links(note_text)
    html_images = parser.extract_referenced_images(note_text)

    # Filter out external links
    local_links = [(text, url) for text, url in markdown_links if not parser.is_external_url(url)]

    LOGGER.info(f"Found local links: {[url for _, url in local_links]}")

    # Augment the remote path with links to our media files
    # We choose to use the preview images even if the local paths are pointed
    # to the full quality versions, since this is how we want to render them on first load
    path_to_remote = {
        **path_to_remote,
        **{
            Path(asset.local_path).with_suffix("").name: asset.remote_preview_path
            for asset in note.assets
        },
    }

    # [(text, local link, remote link)]
    to_replace = []

    for text, local_link in local_links:
        # Remove any relative path indicators and file extension
        clean_link = Path(local_link.lstrip("./")).with_suffix("").name

        # Find the closest match in our path_to_remote index
        closest_match = process.extractOne(clean_link, path_to_remote.keys())
        if closest_match and closest_match[1] >= 95:
            remote_path = path_to_remote[closest_match[0]]
            to_replace.append((text, local_link, remote_path))
            LOGGER.info(f"Converting link: {local_link} -> {remote_path}")
        else:
            LOGGER.warning(f"No match found for local link: {clean_link}")

    # The combination of text & link should be enough to uniquely identify link
    # location and swap with the correct link
    #
    # We can't do this exclusively with local_path because some files may
    # share a common prefix and this will result in incorrect replacement behavior
    for text, local_link, remote_path in to_replace:
        search_text = f"[{text}]({local_link})"
        replace_text = f"[{text}]({remote_path})"
        note_text = note_text.replace(search_text, replace_text)
        LOGGER.info(f"Replaced text: {search_text} -> {replace_text}")

    # Same replacement logic for raw images
    for local_link in html_images:
        if not parser.is_external_url(local_link):
            # Remove any relative path indicators and file extension
            clean_link = Path(local_link.lstrip("./")).with_suffix("").name
            closest_match = process.extractOne(clean_link, path_to_remote.keys())
            if closest_match and closest_match[1] >= 95:
                remote_path = path_to_remote[closest_match[0]]
                note_text = note_text.replace(local_link, remote_path)
                LOGGER.info(f"Replaced image: {local_link} -> {remote_path}")
            else:
                LOGGER.warning(f"No match found for local image: {clean_link}")

    # Treat escape characters specially, since these are used as bash coloring
    note_text = note_text.replace("\\x1b", "\x1b")
    note_text = note_text.replace("\\u001b", "\u001b")

    # Remove other escaped characters unless we are escaping the escape
    note_text = sub(r"([^\\])\\", r"\1", note_text)

    return note_text
