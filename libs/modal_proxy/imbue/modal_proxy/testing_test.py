from pathlib import Path

import pytest

from imbue.modal_proxy.data_types import FileEntryType
from imbue.modal_proxy.errors import ModalProxyError
from imbue.modal_proxy.errors import ModalProxyNotFoundError
from imbue.modal_proxy.testing import TestingImage
from imbue.modal_proxy.testing import TestingModalInterface


@pytest.fixture
def testing_root(tmp_path: Path) -> Path:
    root = tmp_path / "modal_testing"
    root.mkdir()
    return root


@pytest.fixture
def modal(testing_root: Path) -> TestingModalInterface:
    return TestingModalInterface(root_dir=testing_root)


# ---------------------------------------------------------------------------
# Environment tests
# ---------------------------------------------------------------------------


def test_environment_create(modal: TestingModalInterface) -> None:
    modal.environment_create("test-env")
    assert "test-env" in modal._environments


# ---------------------------------------------------------------------------
# App tests
# ---------------------------------------------------------------------------


def test_app_create(modal: TestingModalInterface) -> None:
    app = modal.app_create("my-app")
    assert app.get_name() == "my-app"
    assert app.get_app_id().startswith("ap-")


def test_app_lookup_creates_if_missing(modal: TestingModalInterface) -> None:
    app = modal.app_lookup("my-app", create_if_missing=True, environment_name="env1")
    assert app.get_name() == "my-app"


def test_app_lookup_raises_when_not_found(modal: TestingModalInterface) -> None:
    modal.environment_create("env1")
    with pytest.raises(ModalProxyNotFoundError):
        modal.app_lookup("nonexistent", create_if_missing=False, environment_name="env1")


def test_app_lookup_caches_by_name_and_env(modal: TestingModalInterface) -> None:
    app1 = modal.app_lookup("my-app", create_if_missing=True, environment_name="env1")
    app2 = modal.app_lookup("my-app", create_if_missing=True, environment_name="env1")
    assert app1.get_app_id() == app2.get_app_id()


def test_app_run_yields_self(modal: TestingModalInterface) -> None:
    app = modal.app_create("my-app")
    gen = app.run(environment_name="test")
    yielded_app = next(gen)
    assert yielded_app.get_app_id() == app.get_app_id()


# ---------------------------------------------------------------------------
# Image tests
# ---------------------------------------------------------------------------


def test_image_debian_slim(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    assert image.get_object_id().startswith("img-debian-")


def test_image_from_registry(modal: TestingModalInterface) -> None:
    image = modal.image_from_registry("python:3.11-slim")
    assert "python" in image.get_object_id()


def test_image_from_id(modal: TestingModalInterface) -> None:
    image = modal.image_from_id("img-existing-123")
    assert image.get_object_id() == "img-existing-123"


def test_image_apt_install_returns_new_image(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    new_image = image.apt_install("tmux", "curl")
    assert isinstance(new_image, TestingImage)


def test_image_dockerfile_commands_returns_new_image(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    new_image = image.dockerfile_commands(["RUN echo hello"])
    assert new_image.get_object_id() != image.get_object_id()


# ---------------------------------------------------------------------------
# Volume tests
# ---------------------------------------------------------------------------


def test_volume_from_name_creates(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    assert vol.get_name() == "test-vol"


def test_volume_from_name_raises_when_not_found(modal: TestingModalInterface) -> None:
    with pytest.raises(ModalProxyNotFoundError):
        modal.volume_from_name("nonexistent", create_if_missing=False, environment_name="env1")


def test_volume_write_and_read(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    vol.write_files({"/data/hello.txt": b"world"})
    content = vol.read_file("/data/hello.txt")
    assert content == b"world"


def test_volume_listdir(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    vol.write_files({"/mydir/a.txt": b"a", "/mydir/b.txt": b"b"})
    entries = vol.listdir("/mydir")
    paths = [e.path for e in entries]
    assert "mydir/a.txt" in paths
    assert "mydir/b.txt" in paths
    assert all(e.type == FileEntryType.FILE for e in entries)


def test_volume_listdir_shows_directories(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    vol.write_files({"/parent/child/file.txt": b"x"})
    entries = vol.listdir("/parent")
    assert len(entries) == 1
    assert entries[0].type == FileEntryType.DIRECTORY


def test_volume_listdir_not_found(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    with pytest.raises(ModalProxyNotFoundError):
        vol.listdir("/nonexistent")


def test_volume_read_file_not_found(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    with pytest.raises(ModalProxyNotFoundError):
        vol.read_file("/nonexistent.txt")


def test_volume_remove_file(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    vol.write_files({"/file.txt": b"data"})
    vol.remove_file("/file.txt")
    with pytest.raises(ModalProxyNotFoundError):
        vol.read_file("/file.txt")


def test_volume_remove_directory_recursive(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    vol.write_files({"/dir/a.txt": b"a", "/dir/b.txt": b"b"})
    vol.remove_file("/dir", recursive=True)
    with pytest.raises(ModalProxyNotFoundError):
        vol.listdir("/dir")


def test_volume_remove_directory_without_recursive_fails(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    vol.write_files({"/dir/a.txt": b"a"})
    with pytest.raises(ModalProxyError):
        vol.remove_file("/dir", recursive=False)


def test_volume_remove_not_found(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    with pytest.raises(ModalProxyNotFoundError):
        vol.remove_file("/nonexistent.txt")


def test_volume_list(modal: TestingModalInterface) -> None:
    modal.volume_from_name("vol1", create_if_missing=True, environment_name="env1")
    modal.volume_from_name("vol2", create_if_missing=True, environment_name="env1")
    modal.volume_from_name("vol3", create_if_missing=True, environment_name="env2")
    vols = modal.volume_list(environment_name="env1")
    assert len(vols) == 2


def test_volume_delete(modal: TestingModalInterface) -> None:
    modal.volume_from_name("to-delete", create_if_missing=True, environment_name="env1")
    modal.volume_delete("to-delete", environment_name="env1")
    with pytest.raises(ModalProxyNotFoundError):
        modal.volume_from_name("to-delete", create_if_missing=False, environment_name="env1")


def test_volume_delete_not_found(modal: TestingModalInterface) -> None:
    with pytest.raises(ModalProxyNotFoundError):
        modal.volume_delete("nonexistent", environment_name="env1")


def test_volume_reload_and_commit_are_noop(modal: TestingModalInterface) -> None:
    vol = modal.volume_from_name("test-vol", create_if_missing=True, environment_name="env1")
    vol.reload()
    vol.commit()


# ---------------------------------------------------------------------------
# Sandbox tests
# ---------------------------------------------------------------------------


def test_sandbox_create(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sandbox = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    assert sandbox.get_object_id().startswith("sb-")


def test_sandbox_exec_echo(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sandbox = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    proc = sandbox.exec("echo", "hello world")
    output = proc.get_stdout().read()
    assert "hello world" in output


def test_sandbox_exec_sh_command(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sandbox = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    proc = sandbox.exec("sh", "-c", "echo test123")
    proc.wait()
    output = proc.get_stdout().read()
    assert "test123" in output


def test_sandbox_tags(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sandbox = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    assert sandbox.get_tags() == {}
    sandbox.set_tags({"key": "value", "foo": "bar"})
    tags = sandbox.get_tags()
    assert tags == {"key": "value", "foo": "bar"}


def test_sandbox_snapshot_filesystem(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sandbox = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    snap_image = sandbox.snapshot_filesystem()
    assert snap_image.get_object_id().startswith("snap-")


def test_sandbox_terminate(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sandbox = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    sandbox.terminate()
    with pytest.raises(ModalProxyError, match="terminated"):
        sandbox.exec("echo", "should fail")


def test_sandbox_list(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sb1 = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    sb2 = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    sandboxes = modal.sandbox_list(app_id=app.get_app_id())
    assert len(sandboxes) == 2
    sb1.terminate()
    sandboxes = modal.sandbox_list(app_id=app.get_app_id())
    assert len(sandboxes) == 1


def test_sandbox_from_id(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    sandbox = modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    found = modal.sandbox_from_id(sandbox.get_object_id())
    assert found.get_object_id() == sandbox.get_object_id()


def test_sandbox_from_id_not_found(modal: TestingModalInterface) -> None:
    with pytest.raises(ModalProxyNotFoundError):
        modal.sandbox_from_id("nonexistent-id")


# ---------------------------------------------------------------------------
# Secret tests
# ---------------------------------------------------------------------------


def test_secret_from_dict(modal: TestingModalInterface) -> None:
    secret = modal.secret_from_dict({"API_KEY": "abc123", "EMPTY": None})
    assert isinstance(secret, SecretInterface)


# ---------------------------------------------------------------------------
# Function tests
# ---------------------------------------------------------------------------


def test_function_from_name_not_found(modal: TestingModalInterface) -> None:
    with pytest.raises(ModalProxyNotFoundError):
        modal.function_from_name("nonexistent", app_name="my-app")


# ---------------------------------------------------------------------------
# Deploy tests
# ---------------------------------------------------------------------------


def test_deploy_registers_functions(modal: TestingModalInterface, tmp_path: Path) -> None:
    script = tmp_path / "my_script.py"
    script.write_text("def my_function(x):\n    return x\n\ndef another_func(y):\n    pass\n")
    modal.deploy(script, app_name="test-app")
    func = modal.function_from_name("my_function", app_name="test-app")
    assert func.get_web_url() is not None
    assert "test-app" in (func.get_web_url() or "")


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------


def test_cleanup(modal: TestingModalInterface) -> None:
    image = modal.image_debian_slim()
    app = modal.app_create("test-app")
    modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    modal.sandbox_create(image=image, app=app, timeout=300, cpu=1.0, memory=1024)
    assert modal.get_sandbox_count() == 2
    modal.cleanup()
    assert modal.get_sandbox_count() == 0


# Avoid unused import -- needed for type annotation in test_secret_from_dict
from imbue.modal_proxy.interface import SecretInterface as SecretInterface  # noqa: E402
