import json
from pathlib import Path
from unittest.mock import patch

import pytest

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.core.zygote import ZygoteCommand
from imbue.changelings.core.zygote import ZygoteConfig
from imbue.changelings.core.zygote import ZygoteName
from imbue.changelings.deployment.local import MngNotFoundError
from imbue.changelings.deployment.local import deploy_local
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.subprocess_utils import FinishedProcess
from imbue.imbue_common.primitives import PositiveInt


def _make_zygote_config() -> ZygoteConfig:
    return ZygoteConfig(
        name=ZygoteName("test-agent"),
        command=ZygoteCommand("python server.py"),
        port=PositiveInt(9100),
        description="A test agent",
    )


def _make_paths(tmp_path: Path) -> ChangelingPaths:
    return ChangelingPaths(data_dir=tmp_path / "changelings_data")


def _make_finished_process() -> FinishedProcess:
    return FinishedProcess(
        returncode=0,
        stdout="Agent created",
        stderr="",
        command=("mng", "create"),
        is_output_already_logged=False,
    )


def test_deploy_local_creates_backend_registration(tmp_path: Path) -> None:
    zygote_dir = tmp_path / "zygote"
    zygote_dir.mkdir()
    paths = _make_paths(tmp_path)

    cg = ConcurrencyGroup(name="test")
    with cg:
        with patch(
            "imbue.changelings.deployment.local.shutil.which",
            return_value="/usr/bin/mng",
        ):
            with patch(
                "imbue.concurrency_group.concurrency_group.ConcurrencyGroup.run_process_to_completion",
                return_value=_make_finished_process(),
            ):
                result = deploy_local(
                    zygote_dir=zygote_dir,
                    zygote_config=_make_zygote_config(),
                    agent_name="test-agent",
                    paths=paths,
                    forwarding_server_port=8420,
                    concurrency_group=cg,
                )

    assert result.agent_name == "test-agent"
    assert result.backend_url == "http://127.0.0.1:9100"
    assert "login" in result.login_url
    assert "one_time_code" in result.login_url

    backends_data = json.loads(paths.backends_path.read_text())
    assert str(result.changeling_id) in backends_data


def test_deploy_local_raises_when_mng_not_found(tmp_path: Path) -> None:
    zygote_dir = tmp_path / "zygote"
    zygote_dir.mkdir()
    paths = _make_paths(tmp_path)

    cg = ConcurrencyGroup(name="test")
    with cg:
        with patch(
            "imbue.changelings.deployment.local.shutil.which",
            return_value=None,
        ):
            with pytest.raises(MngNotFoundError, match="mng.*not found"):
                deploy_local(
                    zygote_dir=zygote_dir,
                    zygote_config=_make_zygote_config(),
                    agent_name="test-agent",
                    paths=paths,
                    forwarding_server_port=8420,
                    concurrency_group=cg,
                )
