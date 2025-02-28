from itertools import chain
from pathlib import Path
from re import escape as re_escape
from re import finditer, sub

from rapidfuzz import process
from rich.console import Console

from scribe.logging import LOGGER
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

    # Search for links that haven't been escaped with a \ prior to them
    markdown_matches = finditer(r"[^\\]\[(.*?)\]\((.+?)\)", note_text)
    img_matches = finditer(r"<(img).*?src=[\"'](.*?)[\"'].*?/?>", note_text)
    matches = chain(markdown_matches, img_matches)

    local_links = [
        match
        for match in matches
        if not any(
            [
                "http://" in match.group(2),
                "https://" in match.group(2),
                "www." in match.group(2),
            ]
        )
    ]

    LOGGER.info(f"Found local links: {[match.group(2) for match in local_links]}")

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

    for match in local_links:
        text = match.group(1)
        local_link = match.group(2)

        # Remove any relative path indicators
        local_link = local_link.lstrip("./")

        # Remove any file extension
        local_link = Path(local_link).with_suffix("").name

        # Find the closest match in our path_to_remote index
        closest_match = process.extractOne(local_link, path_to_remote.keys())
        if closest_match and closest_match[1] >= 95:
            remote_path = path_to_remote[closest_match[0]]
            to_replace.append((text, match.group(2), remote_path))
            LOGGER.info(f"Converting link: {match.group(2)} -> {remote_path}")
        else:
            LOGGER.info(f"No match found for local link: {local_link}")

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
    for _text, local_link, remote_path in to_replace:
        note_text = sub(
            f"<img(.*?)src=[\"']{re_escape(local_link)}[\"'](.*?)/?>",
            f'<img\\1src="{re_escape(remote_path)}"\\2/>',
            note_text,
        )

    # Treat escape characters specially, since these are used as bash coloring
    note_text = note_text.replace("\\x1b", "\x1b")
    note_text = note_text.replace("\\u001b", "\u001b")

    # Remove other escaped characters unless we are escaping the escape
    note_text = sub(r"([^\\])\\", r"\1", note_text)

    return note_text
