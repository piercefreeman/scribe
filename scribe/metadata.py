from datetime import datetime
from enum import Enum, unique
from typing import TYPE_CHECKING, Optional

from dateutil import parser as date_parser
from pydantic import BaseModel, validator


if TYPE_CHECKING:
    from scribe.note import Asset


@unique
class FeaturedPhotoPosition(Enum):
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"
    BOTTOM = "bottom"
    TOP = "top"


@unique
class NoteStatus(Enum):
    SCRATCH = "SCRATCH"
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class FeaturedPhotoPayload(BaseModel):
    path: str
    cover: FeaturedPhotoPosition = FeaturedPhotoPosition.CENTER

    asset: Optional["Asset"] = None

    class Config:
        extra = "forbid"


class BuildMetadata(BaseModel):
    style_hash: str | None = None
    code_hash: str | None = None


class NoteMetadata(BaseModel):
    """
    Defines the post metadata that shouldn't be directly visible but drives different
    elements of the note creation engine.

    """

    date: datetime
    tags: list[str] = []
    status: NoteStatus = NoteStatus.SCRATCH
    subtitle: list[str] = []

    external_link: str | None = None

    # Featured photos are paths to photos that should be featured in photo sections
    # They can be separate from those that are contained in the body of the post
    featured_photos: list[str | FeaturedPhotoPayload] = []

    @validator("date", pre=True)
    def validate_date(cls, date):
        if isinstance(date, datetime):
            return date
        return date_parser.parse(date)

    @validator("status", pre=True)
    def validate_status(cls, status):
        if isinstance(status, NoteStatus):
            return status

        if status == "draft":
            return NoteStatus.DRAFT
        elif status == "publish":
            return NoteStatus.PUBLISHED
        else:
            raise ValueError(f"Unknown status: `{status}`")

    class Config:
        extra = "forbid"
