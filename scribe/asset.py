from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from scribe.note import Note

WEB_DPI = 72


class Asset(BaseModel):
    """
    Assets are tied to their parent note. This class normalizes assets
    to be the full quality image. In other words we'll convert preview links
    to their full filepath, following our assumed path patterns.

    """

    root_path: str
    path: Path
    resolution_map: dict[int, str] = {}  # Maps DPI to srcset descriptor (1x, 2x, etc)

    @classmethod
    def from_note(cls, note: "Note", path: Path):
        root_path = note.webpage_path
        path = Path(str(path).replace("-preview", "")).absolute()

        return cls(root_path=root_path, path=path, resolution_map={})

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

    def get_dpi_path(self, dpi: int) -> Path:
        """Get the path for a specific DPI version"""
        return self.path.parent / f"{self.name}-{dpi}dpi{self.path.suffix}"

    @property
    def remote_path(self):
        remote = f"/images/{self.root_path}-{self.name}{self.path.suffix}"
        return remote

    @property
    def remote_preview_path(self):
        remote_preview = f"/images/{self.root_path}-{self.preview_name}{self.path.suffix}"
        return remote_preview

    def get_remote_dpi_path(self, dpi: int) -> str:
        """Get the remote path for a specific DPI version"""
        return f"/images/{self.root_path}-{self.name}-{dpi}dpi{self.path.suffix}"

    def __hash__(self):
        return hash(self.path)
