class HandledBuildError(Exception):
    """An error that has already been properly displayed to the user.
    Parent processes should exit gracefully without showing a traceback."""

    pass
