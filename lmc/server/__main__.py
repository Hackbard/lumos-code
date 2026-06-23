"""`python -m lmc.server` — startet den Lumos CPG-Server (uvicorn)."""
import os
import sys

import uvicorn

from .app import DEFAULT_HOST, DEFAULT_PORT


def main():
    host = os.environ.get("LUMOS_HOST", DEFAULT_HOST)
    port = int(os.environ.get("LUMOS_PORT", DEFAULT_PORT))
    uvicorn.run("lmc.server.app:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    sys.exit(main())