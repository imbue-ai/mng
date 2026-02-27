from pathlib import Path
from typing import Final

import uvicorn

from imbue.changelings.forwarding_server.app import create_forwarding_server
from imbue.changelings.forwarding_server.auth import FileAuthStore
from imbue.changelings.forwarding_server.backend_resolver import StaticBackendResolver

_DEFAULT_HOST: Final[str] = "127.0.0.1"

_DEFAULT_PORT: Final[int] = 8420


def start_forwarding_server(
    data_directory: Path,
    host: str,
    port: int,
) -> None:
    """Start the local forwarding server using uvicorn."""
    auth_store = FileAuthStore(data_directory=data_directory / "auth")
    backend_resolver = StaticBackendResolver(url_by_changeling_name={})

    app = create_forwarding_server(
        auth_store=auth_store,
        backend_resolver=backend_resolver,
        http_client=None,
    )

    uvicorn.run(app, host=host, port=port)
