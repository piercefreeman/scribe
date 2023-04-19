from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scribe.builder import WebsiteBuilder


@pytest.fixture()
def builder():
    return WebsiteBuilder()

@pytest.fixture()
def note_directory():
    with TemporaryDirectory() as directory:
        yield Path(directory)
