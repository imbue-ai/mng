import pytest

from imbue.mng_claude_http.primitives import HttpPort


def test_http_port_accepts_valid_port() -> None:
    port = HttpPort(8080)
    assert port == 8080


def test_http_port_accepts_min_value() -> None:
    port = HttpPort(1)
    assert port == 1


def test_http_port_accepts_max_value() -> None:
    port = HttpPort(65535)
    assert port == 65535


def test_http_port_rejects_zero() -> None:
    with pytest.raises(ValueError, match="Port must be between"):
        HttpPort(0)


def test_http_port_rejects_negative() -> None:
    with pytest.raises(ValueError, match="Port must be between"):
        HttpPort(-1)


def test_http_port_rejects_above_65535() -> None:
    with pytest.raises(ValueError, match="Port must be between"):
        HttpPort(65536)
