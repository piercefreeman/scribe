from pathlib import Path
from tempfile import TemporaryDirectory

from scribe.builder import WebsiteBuilder

import pytest


@pytest.fixture()
def builder():
    return WebsiteBuilder()

@pytest.fixture()
def note_directory():
    with TemporaryDirectory() as directory:
        yield Path(directory)
