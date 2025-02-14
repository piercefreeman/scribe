from pathlib import Path

import uvicorn
from click import command, option
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.responses import FileResponse


def runserver(directory, port):
    """
    Local preview of website
    """
    app = FastAPI()
    directory = Path(directory)

    @app.get("/{path:path}")
    def read_root(path):
        # Blank paths should be index files
        if path == "":
            path = "index"

        # Proxy html files that are stored locally
        if "." not in path:
            path = f"{path}.html"

        path = directory / path

        if not path.exists():
            return HTMLResponse(status_code=400)

        return FileResponse(path)

    uvicorn.run(app, host="0.0.0.0", port=port)
