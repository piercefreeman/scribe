"""Path resolution utilities for Scribe configuration."""

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def resolve_path(path: str | Path, base_dir: Path | None) -> Path:
    """Resolve a path, making it relative to base_dir if it's relative."""
    path_str = os.path.expanduser(str(path))
    path_obj = Path(path_str)

    # If path is absolute or no base_dir provided, return as-is
    if path_obj.is_absolute() or base_dir is None:
        return path_obj

    # If path is relative and we have a base_dir, resolve relative to base_dir
    return base_dir / path_obj


def resolve_paths_recursively(obj: Any, base_dir: Path) -> None:
    """Recursively resolve Path objects in any data structure."""
    if isinstance(obj, Path):
        # This shouldn't happen at top level, but just in case
        return resolve_path(obj, base_dir)
    elif isinstance(obj, dict):
        # Handle dictionary configs
        for key, value in obj.items():
            if isinstance(value, str | Path):
                # Try to convert string to Path and resolve if it looks like a path
                if isinstance(value, str) and any(
                    char in value for char in ["/", "\\", "."]
                ):
                    try:
                        path_obj = Path(value)
                        obj[key] = str(resolve_path(path_obj, base_dir))
                    except (ValueError, OSError):
                        # Not a valid path, leave as string
                        pass
                elif isinstance(value, Path):
                    obj[key] = str(resolve_path(value, base_dir))
            elif isinstance(value, dict | list):
                resolve_paths_recursively(value, base_dir)
    elif isinstance(obj, list):
        # Handle lists
        for item in obj:
            resolve_paths_recursively(item, base_dir)
    elif isinstance(obj, BaseModel):
        # Handle Pydantic models - use model_fields to get only data fields
        try:
            for field_name in obj.__class__.model_fields:
                attr_value = getattr(obj, field_name)
                if isinstance(attr_value, Path):
                    setattr(obj, field_name, resolve_path(attr_value, base_dir))
                elif isinstance(attr_value, dict | list | BaseModel):
                    resolve_paths_recursively(attr_value, base_dir)
        except (AttributeError, TypeError):
            pass
    elif hasattr(obj, "__dict__"):
        # Handle other objects with attributes (fallback)
        for attr_name, attr_value in obj.__dict__.items():
            if attr_name.startswith("_"):
                continue
            try:
                if isinstance(attr_value, Path):
                    setattr(obj, attr_name, resolve_path(attr_value, base_dir))
                elif isinstance(attr_value, dict | list | BaseModel):
                    resolve_paths_recursively(attr_value, base_dir)
            except (AttributeError, TypeError):
                # Skip read-only attributes, etc.
                continue
