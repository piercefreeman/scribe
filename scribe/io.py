import importlib.resources as pkg_resources
from pathlib import Path


def get_asset_path(path):
    return Path(pkg_resources.path(__package__, path))
