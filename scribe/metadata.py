from datetime import datetime
from enum import Enum, unique
from typing import Optional, Literal
from pathlib import Path

from dateutil import parser as date_parser
from pydantic import BaseModel, ConfigDict, validator

from scribe.asset import Asset


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

    asset: Optional[Asset] = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


@unique
class CompileAssetType(Enum):
    TSX = "tsx"
    CSS = "css"
    HTML = "html"

    @classmethod
    def from_extension(cls, extension: str) -> "CompileAssetType":
        """
        Get the asset type from a file extension
        """
        extension = extension.lower().lstrip(".")
        for asset_type in cls:
            if asset_type.value == extension:
                return asset_type
        raise ValueError(f"Unknown file extension: {extension}")


class CompileAsset(BaseModel):
    """
    Defines an asset that needs to be compiled during the build process.
    Can be initialized with either:
    1. A full specification:
       path: str
       type: CompileAssetType
       output_path: str
    2. A simple path string that will be parsed to determine type and output path:
       "src/components/MyComponent.tsx" -> 
       {
           path: "src/components/MyComponent.tsx",
           type: CompileAssetType.TSX,
           output_path: "src/components/MyComponent.js"
       }
    """
    path: str
    type: CompileAssetType
    output_path: str

    asset: Optional[Asset] = None
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    @validator("type", pre=True)
    def validate_type(cls, type_value):
        if isinstance(type_value, CompileAssetType):
            return type_value
        
        try:
            return CompileAssetType(type_value)
        except ValueError:
            raise ValueError(f"Unknown compile asset type: `{type_value}`")

    @classmethod
    def _get_output_extension(cls, type: CompileAssetType) -> str:
        """
        Get the output file extension for a given asset type
        """
        if type == CompileAssetType.TSX:
            return ".js"
        elif type == CompileAssetType.CSS:
            return ".css"
        elif type == CompileAssetType.HTML:
            return ".html"
        else:
            raise ValueError(f"Unknown asset type: {type}")

    @classmethod
    def _from_path(cls, path: str) -> "CompileAsset":
        """
        Create a CompileAsset from a path string
        """
        path_obj = Path(path)
        try:
            asset_type = CompileAssetType.from_extension(path_obj.suffix)
        except ValueError as e:
            raise ValueError(f"Could not determine asset type for path {path}: {str(e)}")
        
        # Replace the extension for the output path
        output_extension = cls._get_output_extension(asset_type)
        output_path = path_obj.with_suffix(output_extension)
        
        return cls(
            path=str(path_obj),
            type=asset_type,
            output_path=str(output_path)
        )

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, str):
            return cls._from_path(v)
        elif isinstance(v, dict):
            return cls(**v)
        elif isinstance(v, cls):
            return v
        else:
            raise ValueError(f"Invalid CompileAsset format: {v}")


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
    compile: list[CompileAsset] = []

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

    @validator("compile", pre=True)
    def validate_compile(cls, compile_assets):
        if not compile_assets:
            return []
        
        # If we get a list of strings, convert each to a CompileAsset
        return [
            CompileAsset._from_path(asset) if isinstance(asset, str) else asset
            for asset in compile_assets
        ]

    class Config:
        extra = "forbid"
