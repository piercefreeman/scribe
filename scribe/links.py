from itertools import chain
from pathlib import Path
from re import escape as re_escape
from re import finditer, sub

from rapidfuzz import process
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from scribe.exceptions import HandledBuildError
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

    # Swap the local links with their actual remote counterparts
    for match in local_links:
        text = match.group(1)
        local_link = match.group(2)

        filename = Path(local_link).with_suffix("").name
        if filename not in path_to_remote:
            # Find similar filenames using fuzzy matching
            similar_files = process.extract(
                filename,
                path_to_remote.keys(),
                limit=5,
                score_cutoff=50,  # Only show reasonably similar matches
            )

            error_text = Text()
            error_text.append("\nBroken link in ", style="red bold")
            error_text.append(note.filename, style="yellow")
            error_text.append("\nCannot find: ", style="red")
            error_text.append(match.group(0), style="yellow")
            console.print(error_text)

            if similar_files:
                suggestions = Panel(
                    "\n".join(
                        [
                            "[yellow]Did you mean:[/yellow]",
                            *[
                                f"[green]{name}[/green] ({int(score)}% match)"
                                for name, score, _ in similar_files
                            ],
                        ]
                    ),
                    title="Suggestions",
                    border_style="blue",
                )
                console.print(suggestions)

            raise HandledBuildError()

        remote_path = path_to_remote[filename]
        to_replace.append((text, local_link, remote_path))

    # The combination of text & link should be enough to uniquely identify link
    # location and swap with the correct link
    #
    # We can't do this exclusively with local_path because some files may
    # share a common prefix and this will result in incorrect replacement behavior
    for text, local_link, remote_path in to_replace:
        search_text = f"[{text}]({local_link})"
        replace_text = f"[{text}]({remote_path})"
        note_text = note_text.replace(search_text, replace_text)

    # Same replacement logic for raw images
    for text, local_link, remote_path in to_replace:
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
