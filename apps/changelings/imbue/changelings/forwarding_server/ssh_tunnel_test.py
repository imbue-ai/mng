import json
import socket
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import paramiko
import pytest
from pydantic import ValidationError

from imbue.changelings.forwarding_server.backend_resolver import BackendResolverInterface
from imbue.changelings.forwarding_server.backend_resolver import MngCliBackendResolver
from imbue.changelings.forwarding_server.backend_resolver import _parse_agents_from_json
from imbue.changelings.forwarding_server.conftest import FakeMngCli
from imbue.changelings.forwarding_server.ssh_tunnel import RemoteSSHInfo
from imbue.changelings.forwarding_server.ssh_tunnel import SSHTunnelManager
from imbue.changelings.forwarding_server.ssh_tunnel import _relay_data
from imbue.changelings.forwarding_server.ssh_tunnel import _tunnel_accept_loop
from imbue.changelings.forwarding_server.ssh_tunnel import parse_url_host_port
from imbue.changelings.primitives import ServerName
from imbue.mng.primitives import AgentId

_AGENT_A: AgentId = AgentId("agent-00000000000000000000000000000001")
_AGENT_B: AgentId = AgentId("agent-00000000000000000000000000000002")


# -- RemoteSSHInfo tests --


def test_remote_ssh_info_constructs_with_valid_fields() -> None:
    info = RemoteSSHInfo(
        user="root",
        host="example.com",
        port=2222,
        key_path=Path("/tmp/test_key"),
    )
    assert info.user == "root"
    assert info.host == "example.com"
    assert info.port == 2222
    assert info.key_path == Path("/tmp/test_key")


def test_remote_ssh_info_is_frozen() -> None:
    info = RemoteSSHInfo(
        user="root",
        host="example.com",
        port=2222,
        key_path=Path("/tmp/test_key"),
    )
    with pytest.raises(ValidationError):
        info.user = "other"  # type: ignore[misc]


# -- parse_url_host_port tests --


def test_parse_url_host_port_extracts_host_and_port() -> None:
    host, port = parse_url_host_port("http://127.0.0.1:9100")
    assert host == "127.0.0.1"
    assert port == 9100


def test_parse_url_host_port_defaults_to_port_80_for_http() -> None:
    host, port = parse_url_host_port("http://example.com/path")
    assert host == "example.com"
    assert port == 80


def test_parse_url_host_port_defaults_to_port_443_for_https() -> None:
    host, port = parse_url_host_port("https://example.com/path")
    assert host == "example.com"
    assert port == 443


def test_parse_url_host_port_handles_localhost() -> None:
    host, port = parse_url_host_port("http://localhost:8080")
    assert host == "localhost"
    assert port == 8080


# -- _parse_agents_from_json tests --


def _make_agents_json_with_ssh(*agents: tuple[str, dict[str, object] | None]) -> str:
    """Build mng list --json output with optional SSH info per agent."""
    agent_list = []
    for agent_id, ssh in agents:
        agent: dict[str, object] = {"id": agent_id}
        if ssh is not None:
            agent["host"] = {"ssh": ssh}
        else:
            agent["host"] = {}
        agent_list.append(agent)
    return json.dumps({"agents": agent_list})


def test_parse_agents_from_json_extracts_agent_ids() -> None:
    json_str = _make_agents_json_with_ssh(
        (str(_AGENT_A), None),
        (str(_AGENT_B), None),
    )
    result = _parse_agents_from_json(json_str)
    assert _AGENT_A in result.agent_ids
    assert _AGENT_B in result.agent_ids


def test_parse_agents_from_json_extracts_ssh_info() -> None:
    ssh_data = {
        "user": "root",
        "host": "remote.example.com",
        "port": 12345,
        "key_path": "/home/user/.mng/providers/modal/modal_ssh_key",
    }
    json_str = _make_agents_json_with_ssh((str(_AGENT_A), ssh_data))
    result = _parse_agents_from_json(json_str)

    ssh_info = result.ssh_info_by_agent_id.get(str(_AGENT_A))
    assert ssh_info is not None
    assert ssh_info.user == "root"
    assert ssh_info.host == "remote.example.com"
    assert ssh_info.port == 12345
    assert ssh_info.key_path == Path("/home/user/.mng/providers/modal/modal_ssh_key")


def test_parse_agents_from_json_returns_none_ssh_for_local_agents() -> None:
    json_str = _make_agents_json_with_ssh((str(_AGENT_A), None))
    result = _parse_agents_from_json(json_str)

    assert str(_AGENT_A) not in result.ssh_info_by_agent_id


def test_parse_agents_from_json_handles_mixed_local_and_remote() -> None:
    ssh_data = {
        "user": "root",
        "host": "remote.example.com",
        "port": 12345,
        "key_path": "/tmp/key",
    }
    json_str = _make_agents_json_with_ssh(
        (str(_AGENT_A), None),
        (str(_AGENT_B), ssh_data),
    )
    result = _parse_agents_from_json(json_str)

    assert len(result.agent_ids) == 2
    assert str(_AGENT_A) not in result.ssh_info_by_agent_id
    assert str(_AGENT_B) in result.ssh_info_by_agent_id


def test_parse_agents_from_json_returns_empty_for_none() -> None:
    result = _parse_agents_from_json(None)
    assert result.agent_ids == ()
    assert result.ssh_info_by_agent_id == {}


def test_parse_agents_from_json_returns_empty_for_invalid_json() -> None:
    result = _parse_agents_from_json("not json")
    assert result.agent_ids == ()


def test_parse_agents_from_json_skips_agents_with_invalid_ssh() -> None:
    json_str = json.dumps(
        {
            "agents": [
                {
                    "id": str(_AGENT_A),
                    "host": {"ssh": {"user": "root"}},  # missing required fields
                },
            ],
        }
    )
    result = _parse_agents_from_json(json_str)
    assert _AGENT_A in result.agent_ids
    assert str(_AGENT_A) not in result.ssh_info_by_agent_id


# -- MngCliBackendResolver.get_ssh_info tests --


def test_mng_cli_resolver_get_ssh_info_returns_info_for_remote_agent() -> None:
    ssh_data = {
        "user": "root",
        "host": "remote.example.com",
        "port": 12345,
        "key_path": "/tmp/test_key",
    }
    agents_json = _make_agents_json_with_ssh((str(_AGENT_A), ssh_data))
    fake_cli = FakeMngCli(server_logs={}, agents_json=agents_json)
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    ssh_info = resolver.get_ssh_info(_AGENT_A)
    assert ssh_info is not None
    assert ssh_info.host == "remote.example.com"
    assert ssh_info.port == 12345


def test_mng_cli_resolver_get_ssh_info_returns_none_for_local_agent() -> None:
    agents_json = _make_agents_json_with_ssh((str(_AGENT_A), None))
    fake_cli = FakeMngCli(server_logs={}, agents_json=agents_json)
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    assert resolver.get_ssh_info(_AGENT_A) is None


def test_mng_cli_resolver_get_ssh_info_returns_none_for_unknown_agent() -> None:
    agents_json = _make_agents_json_with_ssh((str(_AGENT_A), None))
    fake_cli = FakeMngCli(server_logs={}, agents_json=agents_json)
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    assert resolver.get_ssh_info(_AGENT_B) is None


# -- BackendResolverInterface.get_ssh_info default --


def test_backend_resolver_interface_default_get_ssh_info_returns_none() -> None:
    """The base class default get_ssh_info returns None for all agents."""

    class MinimalResolver(BackendResolverInterface):
        def get_backend_url(self, agent_id: AgentId, server_name: ServerName) -> str | None:
            return None

        def list_known_agent_ids(self) -> tuple[AgentId, ...]:
            return ()

        def list_servers_for_agent(self, agent_id: AgentId) -> tuple[ServerName, ...]:
            return ()

    resolver = MinimalResolver()
    assert resolver.get_ssh_info(_AGENT_A) is None


# -- SSHTunnelManager tests --


def test_tunnel_manager_cleanup_without_tunnels() -> None:
    """Cleanup should work even when no tunnels have been created."""
    manager = SSHTunnelManager()
    manager.cleanup()


def test_tunnel_manager_get_tmpdir_creates_secure_directory() -> None:
    """The temporary directory should have 0o700 permissions."""
    manager = SSHTunnelManager()
    try:
        tmpdir = manager._get_tmpdir()
        assert tmpdir.exists()
        stat = tmpdir.stat()
        # 0o700 = owner read/write/execute only
        assert stat.st_mode & 0o777 == 0o700
    finally:
        manager.cleanup()


def test_tunnel_manager_get_tmpdir_returns_same_path() -> None:
    """Multiple calls to _get_tmpdir return the same directory."""
    manager = SSHTunnelManager()
    try:
        dir1 = manager._get_tmpdir()
        dir2 = manager._get_tmpdir()
        assert dir1 == dir2
    finally:
        manager.cleanup()


def test_wait_for_socket_returns_immediately_when_exists(tmp_path: Path) -> None:
    """_wait_for_socket returns immediately when the socket file already exists."""
    from imbue.changelings.forwarding_server.ssh_tunnel import _wait_for_socket

    sock_path = tmp_path / "test.sock"
    sock_path.touch()  # Create the file
    start = time.monotonic()
    _wait_for_socket(sock_path, timeout=5.0)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0


def test_ssh_connection_is_active_returns_false_for_closed() -> None:
    """_SSHConnection.is_active returns False when transport is None."""
    from imbue.changelings.forwarding_server.ssh_tunnel import _SSHConnection

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.get_transport.return_value = None
    conn = _SSHConnection(client=mock_client)
    assert conn.is_active() is False


def test_ssh_connection_is_active_returns_true_for_active() -> None:
    """_SSHConnection.is_active returns True when transport is active."""
    from imbue.changelings.forwarding_server.ssh_tunnel import _SSHConnection

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_transport = MagicMock(spec=paramiko.Transport)
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport
    conn = _SSHConnection(client=mock_client)
    assert conn.is_active() is True


def test_ssh_connection_close_calls_client_close() -> None:
    """_SSHConnection.close delegates to the underlying SSHClient."""
    from imbue.changelings.forwarding_server.ssh_tunnel import _SSHConnection

    mock_client = MagicMock(spec=paramiko.SSHClient)
    conn = _SSHConnection(client=mock_client)
    conn.close()
    mock_client.close.assert_called_once()


def test_ssh_connection_transport_raises_when_closed() -> None:
    """_SSHConnection.transport raises SSHTunnelError when transport is None."""
    from imbue.changelings.forwarding_server.ssh_tunnel import SSHTunnelError
    from imbue.changelings.forwarding_server.ssh_tunnel import _SSHConnection

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.get_transport.return_value = None
    conn = _SSHConnection(client=mock_client)
    with pytest.raises(SSHTunnelError):
        _ = conn.transport


# -- _relay_data tests --


def test_relay_data_forwards_between_socket_pair() -> None:
    """Data sent on one end of a socketpair reaches the other via relay."""
    # Create two socketpairs to simulate the two relay endpoints
    app_sock, relay_sock_a = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    channel_sock, relay_sock_b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

    # Create a mock paramiko channel using the channel_sock
    mock_channel = MagicMock(spec=paramiko.Channel)

    # Track data sent to the channel
    received_by_channel: list[bytes] = []

    def mock_sendall(data: bytes) -> None:
        received_by_channel.append(data)
        relay_sock_b.sendall(data)

    def mock_recv(size: int) -> bytes:
        return relay_sock_b.recv(size)

    def mock_recv_ready() -> bool:
        return True

    def mock_fileno() -> int:
        return relay_sock_b.fileno()

    mock_channel.sendall = mock_sendall
    mock_channel.recv = mock_recv
    mock_channel.recv_ready = mock_recv_ready
    mock_channel.fileno = mock_fileno
    mock_channel.close = MagicMock()

    # Start relay in a thread
    relay_thread = threading.Thread(target=_relay_data, args=(relay_sock_a, mock_channel), daemon=True)
    relay_thread.start()

    # Send data from app_sock (simulating httpx client)
    app_sock.sendall(b"hello from client")
    time.sleep(0.1)

    # The channel should have received the data
    assert len(received_by_channel) > 0
    assert b"hello from client" in b"".join(received_by_channel)

    # Send data back through channel socket (simulating remote backend response)
    channel_sock.sendall(b"hello from backend")
    time.sleep(0.1)
    data = app_sock.recv(4096)
    assert data == b"hello from backend"

    # Close sockets to stop relay
    app_sock.close()
    channel_sock.close()
    relay_thread.join(timeout=3.0)


# -- _tunnel_accept_loop tests --


def test_tunnel_accept_loop_forwards_connections(tmp_path: Path) -> None:
    """The accept loop creates Unix sockets and forwards data through a mock transport."""
    sock_path = tmp_path / "test.sock"
    shutdown_event = threading.Event()

    # Create a mock transport
    mock_transport = MagicMock(spec=paramiko.Transport)

    # Create a socketpair for the "SSH channel" side
    channel_remote, channel_local = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

    # Set up mock channel
    mock_channel = MagicMock(spec=paramiko.Channel)
    mock_channel.recv_ready.return_value = True
    mock_channel.fileno.return_value = channel_local.fileno()
    mock_channel.recv.side_effect = lambda size: channel_local.recv(size)
    mock_channel.sendall.side_effect = lambda data: channel_local.sendall(data)
    mock_channel.close.side_effect = lambda: channel_local.close()

    mock_transport.open_channel.return_value = mock_channel

    # Start the accept loop in a thread
    accept_thread = threading.Thread(
        target=_tunnel_accept_loop,
        args=(sock_path, mock_transport, "127.0.0.1", 9100, shutdown_event),
        daemon=True,
    )
    accept_thread.start()

    # Wait for socket to appear
    for _ in range(50):
        if sock_path.exists():
            break
        time.sleep(0.05)
    assert sock_path.exists()

    # Connect to the tunnel socket
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(sock_path))

    # Send data through the tunnel
    client.sendall(b"test request")
    time.sleep(0.1)

    # The channel_remote should have received it (via the channel mock)
    data = channel_remote.recv(4096)
    assert data == b"test request"

    # Send response back
    channel_remote.sendall(b"test response")
    time.sleep(0.1)
    response = client.recv(4096)
    assert response == b"test response"

    # Clean up
    client.close()
    channel_remote.close()
    shutdown_event.set()
    accept_thread.join(timeout=3.0)


def test_tunnel_accept_loop_handles_channel_open_failure(tmp_path: Path) -> None:
    """When open_channel fails, the accepted client socket is closed gracefully."""
    sock_path = tmp_path / "fail.sock"
    shutdown_event = threading.Event()

    mock_transport = MagicMock(spec=paramiko.Transport)
    mock_transport.open_channel.side_effect = paramiko.SSHException("Channel denied")

    accept_thread = threading.Thread(
        target=_tunnel_accept_loop,
        args=(sock_path, mock_transport, "127.0.0.1", 9100, shutdown_event),
        daemon=True,
    )
    accept_thread.start()

    for _ in range(50):
        if sock_path.exists():
            break
        time.sleep(0.05)

    # Connect - the connection should be accepted then closed
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(sock_path))
    client.settimeout(1.0)

    # The tunnel should close the client socket since channel open failed
    time.sleep(0.2)
    try:
        data = client.recv(4096)
        # Empty data means the other end closed
        assert data == b""
    except socket.timeout:
        pass  # Acceptable - client may have been closed already

    client.close()
    shutdown_event.set()
    accept_thread.join(timeout=3.0)


def test_tunnel_accept_loop_shutdown_event_stops_loop(tmp_path: Path) -> None:
    """Setting the shutdown event causes the accept loop to exit."""
    sock_path = tmp_path / "shutdown.sock"
    shutdown_event = threading.Event()

    mock_transport = MagicMock(spec=paramiko.Transport)

    accept_thread = threading.Thread(
        target=_tunnel_accept_loop,
        args=(sock_path, mock_transport, "127.0.0.1", 9100, shutdown_event),
        daemon=True,
    )
    accept_thread.start()

    for _ in range(50):
        if sock_path.exists():
            break
        time.sleep(0.05)

    shutdown_event.set()
    accept_thread.join(timeout=3.0)
    assert not accept_thread.is_alive()
