from importlib.resources import as_file, files
from pathlib import Path


def get_asset_path(path):
    with as_file(files(__package__) / path) as file_path:
        return Path(file_path)
