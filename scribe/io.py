from pathlib import Path
from pkg_resources import resource_filename


def get_asset_path(path):
    return Path(resource_filename(__name__, path))
