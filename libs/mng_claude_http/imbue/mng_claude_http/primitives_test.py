import pytest

from imbue.mng_claude_http.primitives import HttpPort
from imbue.mng_claude_http.primitives import WebSocketUrl


class TestHttpPort:
    def test_valid_port(self) -> None:
        port = HttpPort(8080)
        assert port == 8080

    def test_min_port(self) -> None:
        port = HttpPort(1)
        assert port == 1

    def test_max_port(self) -> None:
        port = HttpPort(65535)
        assert port == 65535

    def test_zero_port_raises(self) -> None:
        with pytest.raises(ValueError, match="Port must be between"):
            HttpPort(0)

    def test_negative_port_raises(self) -> None:
        with pytest.raises(ValueError, match="Port must be between"):
            HttpPort(-1)

    def test_too_large_port_raises(self) -> None:
        with pytest.raises(ValueError, match="Port must be between"):
            HttpPort(65536)


class TestWebSocketUrl:
    def test_valid_url(self) -> None:
        url = WebSocketUrl("ws://localhost:8080")
        assert url == "ws://localhost:8080"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            WebSocketUrl("")
