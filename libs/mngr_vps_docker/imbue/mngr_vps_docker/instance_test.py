"""Tests for VPS Docker provider instance utilities."""

from pathlib import Path

from imbue.mngr_vps_docker.instance import _parse_build_args
from imbue.mngr_vps_docker.instance import _remove_host_from_known_hosts

_DEFAULTS = {
    "default_region": "ewr",
    "default_plan": "vc2-1c-1gb",
    "default_os_id": 2136,
}


def test_parse_build_args_defaults_when_none() -> None:
    region, plan, os_id, docker_args = _parse_build_args(None, **_DEFAULTS)
    assert region == "ewr"
    assert plan == "vc2-1c-1gb"
    assert os_id == 2136
    assert docker_args == ()


def test_parse_build_args_defaults_when_empty() -> None:
    region, plan, os_id, docker_args = _parse_build_args([], **_DEFAULTS)
    assert region == "ewr"
    assert plan == "vc2-1c-1gb"
    assert os_id == 2136
    assert docker_args == ()


def test_parse_build_args_vps_region() -> None:
    region, plan, os_id, docker_args = _parse_build_args(["--vps-region=lax"], **_DEFAULTS)
    assert region == "lax"
    assert plan == "vc2-1c-1gb"
    assert os_id == 2136
    assert docker_args == ()


def test_parse_build_args_vps_plan() -> None:
    region, plan, os_id, docker_args = _parse_build_args(["--vps-plan=vc2-2c-4gb"], **_DEFAULTS)
    assert plan == "vc2-2c-4gb"


def test_parse_build_args_vps_os() -> None:
    region, plan, os_id, docker_args = _parse_build_args(["--vps-os=9999"], **_DEFAULTS)
    assert os_id == 9999


def test_parse_build_args_docker_args_passthrough() -> None:
    region, plan, os_id, docker_args = _parse_build_args(
        ["--file=Dockerfile", "."], **_DEFAULTS
    )
    assert region == "ewr"
    assert docker_args == ("--file=Dockerfile", ".")


def test_parse_build_args_mixed_vps_and_docker() -> None:
    region, plan, os_id, docker_args = _parse_build_args(
        ["--vps-plan=vc2-2c-4gb", "--file=Dockerfile", "--vps-region=lax", "."],
        **_DEFAULTS,
    )
    assert region == "lax"
    assert plan == "vc2-2c-4gb"
    assert os_id == 2136
    assert docker_args == ("--file=Dockerfile", ".")


def test_parse_build_args_all_vps_overrides() -> None:
    region, plan, os_id, docker_args = _parse_build_args(
        ["--vps-region=sjc", "--vps-plan=vc2-4c-8gb", "--vps-os=1234"],
        **_DEFAULTS,
    )
    assert region == "sjc"
    assert plan == "vc2-4c-8gb"
    assert os_id == 1234
    assert docker_args == ()


def test_remove_host_from_known_hosts_port_22(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(
        "192.168.1.100 ssh-ed25519 AAAA key1\n"
        "192.168.1.101 ssh-ed25519 BBBB key2\n"
    )
    _remove_host_from_known_hosts(known_hosts, "192.168.1.100", 22)
    result = known_hosts.read_text()
    assert "192.168.1.100" not in result
    assert "192.168.1.101" in result


def test_remove_host_from_known_hosts_nonstandard_port(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(
        "[192.168.1.100]:2222 ssh-ed25519 AAAA key1\n"
        "192.168.1.100 ssh-ed25519 BBBB key2\n"
    )
    _remove_host_from_known_hosts(known_hosts, "192.168.1.100", 2222)
    result = known_hosts.read_text()
    assert "[192.168.1.100]:2222" not in result
    # The port-22 entry should remain
    assert "192.168.1.100 ssh-ed25519 BBBB key2" in result


def test_remove_host_from_known_hosts_file_not_exists(tmp_path: Path) -> None:
    known_hosts = tmp_path / "nonexistent"
    # Should not raise
    _remove_host_from_known_hosts(known_hosts, "192.168.1.100", 22)


def test_remove_host_from_known_hosts_no_match(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    original = "192.168.1.101 ssh-ed25519 AAAA key1\n"
    known_hosts.write_text(original)
    _remove_host_from_known_hosts(known_hosts, "192.168.1.100", 22)
    assert known_hosts.read_text() == original


def test_remove_host_from_known_hosts_empty_file(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("")
    _remove_host_from_known_hosts(known_hosts, "192.168.1.100", 22)
    assert known_hosts.read_text() == ""
