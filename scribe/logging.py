from logging import DEBUG, ERROR, INFO, WARNING, basicConfig, getLogger
from os import getenv

# Configure logging based on environment variable
log_level_map = {
    "DEBUG": DEBUG,
    "INFO": INFO,
    "WARNING": WARNING,
    "ERROR": ERROR,
}
log_level = log_level_map.get(getenv("SCRIBE_LOG_LEVEL", "WARNING").upper(), WARNING)

basicConfig(
    level=log_level, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

LOGGER = getLogger("scribe")
