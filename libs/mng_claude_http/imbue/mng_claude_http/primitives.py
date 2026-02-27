from imbue.imbue_common.primitives import NonEmptyStr


class WebSocketUrl(NonEmptyStr):
    """A WebSocket URL (ws:// or wss://)."""


class HttpPort(int):
    """An HTTP port number."""

    def __new__(cls, value: int) -> "HttpPort":
        if not (1 <= value <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {value}")
        return super().__new__(cls, value)
