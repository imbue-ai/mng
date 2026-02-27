from pathlib import Path
from typing import Final

import uvicorn

from imbue.changelings.forwarding_server.app import create_forwarding_server
from imbue.changelings.forwarding_server.auth import FileAuthStore
from imbue.changelings.forwarding_server.backend_resolver import BACKENDS_FILENAME
from imbue.changelings.forwarding_server.backend_resolver import FileBackendResolver

_DEFAULT_HOST: Final[str] = "127.0.0.1"

_DEFAULT_PORT: Final[int] = 8420


def start_forwarding_server(
    data_directory: Path,
    host: str,
    port: int,
) -> None:
    """Start the local forwarding server using uvicorn.

    The server reads backend mappings from a backends.json file in the data directory,
    which allows newly deployed changelings to be discovered without restarting.
    """
    auth_store = FileAuthStore(data_directory=data_directory / "auth")
    backend_resolver = FileBackendResolver(
        backends_path=data_directory / BACKENDS_FILENAME,
    )

    app = create_forwarding_server(
        auth_store=auth_store,
        backend_resolver=backend_resolver,
        http_client=None,
    )

    uvicorn.run(app, host=host, port=port)
