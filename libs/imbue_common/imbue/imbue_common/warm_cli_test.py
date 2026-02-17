import os
import socket
import subprocess
import sys
import time
import types
from pathlib import Path
from uuid import uuid4

import click
import pytest

from imbue.imbue_common.warm_cli import _default_socket_path
from imbue.imbue_common.warm_cli import _recv_fds
from imbue.imbue_common.warm_cli import _resolve_click_callback
from imbue.imbue_common.warm_cli import _run_entry_func
from imbue.imbue_common.warm_cli import _send_fds


def test_resolve_click_callback_returns_plain_function_as_is() -> None:
    def my_func() -> None:
        pass

    result = _resolve_click_callback(my_func)

    assert result is my_func


def test_resolve_click_callback_extracts_callback_from_click_command() -> None:
    @click.command()
    def my_command() -> None:
        pass

    result = _resolve_click_callback(my_command)

    assert result is not my_command
    assert isinstance(result, types.FunctionType)
    assert result.__name__ == "my_command"


def test_resolve_click_callback_raises_for_command_without_callback() -> None:
    cmd = click.Command(name="empty")

    with pytest.raises(TypeError, match="has no callback function"):
        _resolve_click_callback(cmd)


def test_run_entry_func_returns_zero_for_successful_click_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["test_cmd"])

    @click.command()
    def success_cmd() -> None:
        pass

    exit_code = _run_entry_func(success_cmd)

    assert exit_code == 0


def test_run_entry_func_returns_int_result_from_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["test_cmd"])

    @click.command()
    def returns_42() -> int:
        return 42

    exit_code = _run_entry_func(returns_42)

    assert exit_code == 42


def test_run_entry_func_returns_exit_code_from_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["test_cmd"])

    @click.command()
    def exits_with_3() -> None:
        raise SystemExit(3)

    exit_code = _run_entry_func(exits_with_3)

    assert exit_code == 3


def test_run_entry_func_returns_one_for_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["test_cmd"])

    @click.command()
    def raises_value_error() -> None:
        raise ValueError("something went wrong")

    exit_code = _run_entry_func(raises_value_error)

    assert exit_code == 1


def test_default_socket_path_uses_module_and_function_name() -> None:
    def my_func() -> None:
        pass

    path = _default_socket_path(my_func)

    assert "warm_cli" in str(path)
    assert "my_func" in str(path)
    assert str(path).startswith("/tmp/")
    assert str(path).endswith(".sock")


def test_send_and_recv_fds_round_trips_file_descriptors() -> None:
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    socket_path = Path(f"/tmp/warm_cli_test_fds_{uuid4().hex}.sock")
    try:
        server_sock.bind(str(socket_path))
        server_sock.listen(1)

        client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_sock.connect(str(socket_path))

        conn, _ = server_sock.accept()

        # Send a pair of pipe fds
        read_fd, write_fd = os.pipe()
        _send_fds(client_sock, [read_fd, write_fd], data=b"hello")

        data, received_fds = _recv_fds(conn, 2)

        assert data == b"hello"
        assert len(received_fds) == 2

        # Verify the received fds are functional: write through one, read from the other
        os.write(received_fds[1], b"test data")
        os.close(received_fds[1])
        result = os.read(received_fds[0], 100)
        assert result == b"test data"

        os.close(received_fds[0])
        os.close(read_fd)
        os.close(write_fd)
        client_sock.close()
        conn.close()
    finally:
        server_sock.close()
        socket_path.unlink(missing_ok=True)


def test_warm_cli_end_to_end_cold_and_warm_paths(tmp_path: Path) -> None:
    """Integration test that verifies both cold and warm paths work correctly."""
    unique_id = uuid4().hex
    # Use /tmp directly to avoid AF_UNIX path length limits (~108 bytes)
    socket_path = Path(f"/tmp/wc_test_{unique_id[:12]}.sock")

    script_content = f"""
import click
from pathlib import Path
from imbue.imbue_common.warm_cli import warm_cli

@click.command()
@click.argument("name")
def hello(name):
    click.echo(f"Hello, {{name}}!")

if __name__ == "__main__":
    warm_cli(hello, socket_path=Path("{socket_path}"))
"""
    script_file = tmp_path / f"warm_test_script_{unique_id}.py"
    script_file.write_text(script_content)

    try:
        # Cold path
        cold_result = subprocess.run(
            [sys.executable, str(script_file), "ColdWorld"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert cold_result.returncode == 0
        assert "Hello, ColdWorld!" in cold_result.stdout

        # Wait for the warm successor to bind
        _poll_until_socket_exists(socket_path, timeout_seconds=5)

        # Warm path
        warm_result = subprocess.run(
            [sys.executable, str(script_file), "WarmWorld"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert warm_result.returncode == 0
        assert "Hello, WarmWorld!" in warm_result.stdout
    finally:
        socket_path.unlink(missing_ok=True)


def test_warm_cli_propagates_nonzero_exit_code(tmp_path: Path) -> None:
    """Verify that non-zero exit codes from the CLI are propagated back."""
    unique_id = uuid4().hex
    socket_path = Path(f"/tmp/wc_exit_{unique_id[:12]}.sock")

    script_content = f"""
import click
import sys
from pathlib import Path
from imbue.imbue_common.warm_cli import warm_cli

@click.command()
def fail_cmd():
    sys.exit(7)

if __name__ == "__main__":
    warm_cli(fail_cmd, socket_path=Path("{socket_path}"))
"""
    script_file = tmp_path / f"warm_exit_script_{unique_id}.py"
    script_file.write_text(script_content)

    try:
        # Cold path should propagate exit code 7
        result = subprocess.run(
            [sys.executable, str(script_file)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 7

        # Wait for warm successor
        _poll_until_socket_exists(socket_path, timeout_seconds=5)

        # Warm path should also propagate exit code 7
        warm_result = subprocess.run(
            [sys.executable, str(script_file)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert warm_result.returncode == 7
    finally:
        socket_path.unlink(missing_ok=True)


def test_warm_cli_passes_argv_to_warm_server(tmp_path: Path) -> None:
    """Verify that the warm server receives the correct argv from the client."""
    unique_id = uuid4().hex
    socket_path = Path(f"/tmp/wc_argv_{unique_id[:12]}.sock")
    output_file = tmp_path / f"warm_env_output_{unique_id}.txt"

    script_content = f"""
import os
import sys
import click
from pathlib import Path
from imbue.imbue_common.warm_cli import warm_cli

@click.command()
@click.argument("name")
def dump_env(name):
    output_path = Path("{output_file}")
    output_path.write_text(f"argv={{sys.argv}}\\ncwd={{os.getcwd()}}\\nname={{name}}")

if __name__ == "__main__":
    warm_cli(dump_env, socket_path=Path("{socket_path}"))
"""
    script_file = tmp_path / f"warm_env_script_{unique_id}.py"
    script_file.write_text(script_content)

    try:
        # Cold path
        subprocess.run(
            [sys.executable, str(script_file), "Alice"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        cold_output = output_file.read_text()
        assert "name=Alice" in cold_output

        # Wait for warm successor
        _poll_until_socket_exists(socket_path, timeout_seconds=5)

        # Warm path with different argument
        subprocess.run(
            [sys.executable, str(script_file), "Bob"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        warm_output = output_file.read_text()
        assert "name=Bob" in warm_output
    finally:
        socket_path.unlink(missing_ok=True)


def _poll_until_socket_exists(socket_path: Path, timeout_seconds: float) -> None:
    """Poll until the socket file exists, raising if it doesn't appear within the timeout."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        time.sleep(0.1)
    raise TimeoutError(f"Socket {socket_path} did not appear within {timeout_seconds}s")
