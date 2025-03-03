from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from scribe.note import Note


class Asset(BaseModel):
    """
    Assets are tied to their parent note. This class normalizes assets
    to be the full quality image. In other words we'll convert preview links
    to their full filepath, following our assumed path patterns.

    """

    root_path: str
    path: Path

    @classmethod
    def from_note(cls, note: "Note", path: Path):
        root_path = note.webpage_path
        path = Path(str(path).replace("-preview", "")).absolute()

        return cls(root_path=root_path, path=path)

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
        preview_path = self.path.parent / f"{self.preview_name}{self.path.suffix}"
        return preview_path

    @property
    def remote_path(self):
        remote = f"/images/{self.root_path}-{self.name}{self.path.suffix}"
        return remote

    @property
    def remote_preview_path(self):
        remote_preview = f"/images/{self.root_path}-{self.preview_name}{self.path.suffix}"
        return remote_preview

    def __hash__(self):
        return hash(self.path)
