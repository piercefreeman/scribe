from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scribe.note import Note


class Asset:
    """
    Assets are tied to their parent note. This class normalizes assets
    to be the full quality image. In other words we'll convert preview links
    to their full filepath, following our assumed path patterns.

    """

    def __init__(self, note: "Note", path: Path):
        self.root_path = note.webpage_path
        self.path = Path(str(path).replace("-preview", "")).absolute()

    @property
    def name(self):
        return Path(self.path).with_suffix("").name

    @property
    def preview_name(self):
        return self.name + "-preview"

    @property
    def local_path(self):
        return self.path

    @property
    def local_preview_path(self):
        return self.path.parent / f"{self.preview_name}{self.path.suffix}"

    @property
    def remote_path(self):
        return f"/images/{self.root_path}-{self.name}{self.path.suffix}"

    @property
    def remote_preview_path(self):
        return f"/images/{self.root_path}-{self.preview_name}{self.path.suffix}"

    def __hash__(self):
        return hash(self.path)
