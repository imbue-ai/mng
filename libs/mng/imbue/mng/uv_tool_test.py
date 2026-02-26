from pathlib import Path

import pytest

from imbue.mng.cli.output_helpers import AbortError
from imbue.mng.uv_tool import ToolRequirement
from imbue.mng.uv_tool import _requirement_to_with_arg
from imbue.mng.uv_tool import build_base_specifier
from imbue.mng.uv_tool import build_uv_tool_install_add
from imbue.mng.uv_tool import build_uv_tool_install_add_git
from imbue.mng.uv_tool import build_uv_tool_install_add_path
from imbue.mng.uv_tool import build_uv_tool_install_command
from imbue.mng.uv_tool import build_uv_tool_install_remove
from imbue.mng.uv_tool import get_base_requirement
from imbue.mng.uv_tool import get_extra_requirements
from imbue.mng.uv_tool import get_receipt_path
from imbue.mng.uv_tool import read_receipt_requirements
from imbue.mng.uv_tool import require_uv_tool_receipt

# =============================================================================
# Tests for ToolRequirement
# =============================================================================


def test_tool_requirement_minimal() -> None:
    """ToolRequirement should create with just a name."""
    req = ToolRequirement(name="mng")
    assert req.name == "mng"
    assert req.specifier is None
    assert req.editable is None
    assert req.git is None


def test_tool_requirement_with_specifier() -> None:
    """ToolRequirement should store version specifiers."""
    req = ToolRequirement(name="mng", specifier=">=0.1.0")
    assert req.specifier == ">=0.1.0"


def test_tool_requirement_with_editable() -> None:
    """ToolRequirement should store editable paths."""
    req = ToolRequirement(name="my-plugin", editable="/path/to/plugin")
    assert req.editable == "/path/to/plugin"


def test_tool_requirement_with_git() -> None:
    """ToolRequirement should store git URLs."""
    req = ToolRequirement(name="my-plugin", git="https://github.com/user/repo.git")
    assert req.git == "https://github.com/user/repo.git"


# =============================================================================
# Tests for _requirement_to_with_arg
# =============================================================================


def test_requirement_to_with_arg_plain_name() -> None:
    """Plain name should produce --with name."""
    req = ToolRequirement(name="mng-opencode")
    assert _requirement_to_with_arg(req) == ("--with", "mng-opencode")


def test_requirement_to_with_arg_with_specifier() -> None:
    """Name with specifier should produce --with name+specifier."""
    req = ToolRequirement(name="mng-opencode", specifier=">=1.0")
    assert _requirement_to_with_arg(req) == ("--with", "mng-opencode>=1.0")


def test_requirement_to_with_arg_editable() -> None:
    """Editable should produce --with-editable path."""
    req = ToolRequirement(name="my-plugin", editable="/path/to/plugin")
    assert _requirement_to_with_arg(req) == ("--with-editable", "/path/to/plugin")


def test_requirement_to_with_arg_git() -> None:
    """Git should produce --with 'name @ git+url'."""
    req = ToolRequirement(name="my-plugin", git="https://github.com/user/repo.git")
    assert _requirement_to_with_arg(req) == ("--with", "my-plugin @ git+https://github.com/user/repo.git")


# =============================================================================
# Tests for get_receipt_path
# =============================================================================


def test_get_receipt_path_returns_none_in_dev_mode() -> None:
    """get_receipt_path should return None when not running from a uv tool venv."""
    # In tests, sys.prefix is the workspace venv which has no uv-receipt.toml
    assert get_receipt_path() is None


# =============================================================================
# Tests for require_uv_tool_receipt
# =============================================================================


def test_require_uv_tool_receipt_raises_in_dev_mode() -> None:
    """require_uv_tool_receipt should raise AbortError outside a uv tool venv."""
    with pytest.raises(AbortError, match="not installed via"):
        require_uv_tool_receipt()


# =============================================================================
# Tests for read_receipt_requirements
# =============================================================================


def test_read_receipt_requirements_minimal(tmp_path: Path) -> None:
    """read_receipt_requirements should parse a minimal receipt."""
    receipt = tmp_path / "uv-receipt.toml"
    receipt.write_text('[tool]\nrequirements = [{ name = "mng" }]\n')

    reqs = read_receipt_requirements(receipt)
    assert len(reqs) == 1
    assert reqs[0].name == "mng"


def test_read_receipt_requirements_with_extras(tmp_path: Path) -> None:
    """read_receipt_requirements should parse a receipt with extra deps."""
    receipt = tmp_path / "uv-receipt.toml"
    receipt.write_text(
        "[tool]\nrequirements = [\n"
        '  { name = "mng" },\n'
        '  { name = "coolname" },\n'
        '  { name = "mng-opencode", editable = "/path/to/opencode" },\n'
        "]\n"
    )

    reqs = read_receipt_requirements(receipt)
    assert len(reqs) == 3
    assert reqs[0].name == "mng"
    assert reqs[1].name == "coolname"
    assert reqs[2].name == "mng-opencode"
    assert reqs[2].editable == "/path/to/opencode"


def test_read_receipt_requirements_with_specifier(tmp_path: Path) -> None:
    """read_receipt_requirements should parse version specifiers."""
    receipt = tmp_path / "uv-receipt.toml"
    receipt.write_text(
        "[tool]\nrequirements = [\n"
        '  { name = "mng", specifier = ">=0.1.0" },\n'
        '  { name = "coolname", specifier = ">=2.0" },\n'
        "]\n"
    )

    reqs = read_receipt_requirements(receipt)
    assert reqs[0].specifier == ">=0.1.0"
    assert reqs[1].specifier == ">=2.0"


def test_read_receipt_requirements_with_git(tmp_path: Path) -> None:
    """read_receipt_requirements should parse git URLs."""
    receipt = tmp_path / "uv-receipt.toml"
    receipt.write_text(
        "[tool]\nrequirements = [\n"
        '  { name = "mng" },\n'
        '  { name = "mng-opencode", git = "https://github.com/imbue-ai/mng.git" },\n'
        "]\n"
    )

    reqs = read_receipt_requirements(receipt)
    assert reqs[1].git == "https://github.com/imbue-ai/mng.git"


# =============================================================================
# Tests for get_base_requirement / get_extra_requirements
# =============================================================================


def test_get_base_requirement_finds_mng() -> None:
    """get_base_requirement should return the mng entry."""
    reqs = [
        ToolRequirement(name="mng", specifier=">=0.1.0"),
        ToolRequirement(name="coolname"),
    ]
    base = get_base_requirement(reqs)
    assert base.name == "mng"
    assert base.specifier == ">=0.1.0"


def test_get_base_requirement_fallback_when_missing() -> None:
    """get_base_requirement should return a plain mng entry if not found."""
    reqs = [ToolRequirement(name="something-else")]
    base = get_base_requirement(reqs)
    assert base.name == "mng"
    assert base.specifier is None


def test_get_extra_requirements_excludes_mng() -> None:
    """get_extra_requirements should return everything except mng."""
    reqs = [
        ToolRequirement(name="mng"),
        ToolRequirement(name="coolname"),
        ToolRequirement(name="mng-opencode"),
    ]
    extras = get_extra_requirements(reqs)
    assert len(extras) == 2
    assert extras[0].name == "coolname"
    assert extras[1].name == "mng-opencode"


# =============================================================================
# Tests for build_base_specifier
# =============================================================================


def test_build_base_specifier_plain() -> None:
    """build_base_specifier should return just the name."""
    assert build_base_specifier(ToolRequirement(name="mng")) == "mng"


def test_build_base_specifier_with_version() -> None:
    """build_base_specifier should include the version specifier."""
    assert build_base_specifier(ToolRequirement(name="mng", specifier=">=0.1.0")) == "mng>=0.1.0"


# =============================================================================
# Tests for build_uv_tool_install_command
# =============================================================================


def test_build_uv_tool_install_command_no_extras() -> None:
    """build_uv_tool_install_command with no extras should produce minimal command."""
    base = ToolRequirement(name="mng")
    cmd = build_uv_tool_install_command(base, [])
    assert cmd == ("uv", "tool", "install", "mng", "--reinstall")


def test_build_uv_tool_install_command_with_extras() -> None:
    """build_uv_tool_install_command should include --with for each extra."""
    base = ToolRequirement(name="mng")
    extras = [
        ToolRequirement(name="coolname"),
        ToolRequirement(name="mng-opencode", editable="/path/to/opencode"),
    ]
    cmd = build_uv_tool_install_command(base, extras)
    assert cmd == (
        "uv",
        "tool",
        "install",
        "mng",
        "--reinstall",
        "--with",
        "coolname",
        "--with-editable",
        "/path/to/opencode",
    )


# =============================================================================
# Tests for build_uv_tool_install_add / add_path / add_git / remove
# =============================================================================


def test_build_uv_tool_install_add_appends_new_dep() -> None:
    """build_uv_tool_install_add should preserve existing extras and append."""
    base = ToolRequirement(name="mng")
    existing = [ToolRequirement(name="coolname")]
    cmd = build_uv_tool_install_add(base, existing, "mng-opencode")
    assert cmd == (
        "uv",
        "tool",
        "install",
        "mng",
        "--reinstall",
        "--with",
        "coolname",
        "--with",
        "mng-opencode",
    )


def test_build_uv_tool_install_add_path() -> None:
    """build_uv_tool_install_add_path should use --with-editable."""
    base = ToolRequirement(name="mng")
    cmd = build_uv_tool_install_add_path(base, [], "/path/to/plugin", "my-plugin")
    assert cmd == (
        "uv",
        "tool",
        "install",
        "mng",
        "--reinstall",
        "--with-editable",
        "/path/to/plugin",
    )


def test_build_uv_tool_install_add_git() -> None:
    """build_uv_tool_install_add_git should use git+ prefixed URL."""
    base = ToolRequirement(name="mng")
    cmd = build_uv_tool_install_add_git(base, [], "https://github.com/user/repo.git")
    assert cmd == (
        "uv",
        "tool",
        "install",
        "mng",
        "--reinstall",
        "--with",
        "git+https://github.com/user/repo.git",
    )


def test_build_uv_tool_install_remove_filters_dep() -> None:
    """build_uv_tool_install_remove should rebuild without the target dep."""
    base = ToolRequirement(name="mng")
    existing = [
        ToolRequirement(name="coolname"),
        ToolRequirement(name="mng-opencode"),
    ]
    cmd = build_uv_tool_install_remove(base, existing, "mng-opencode")
    assert cmd == (
        "uv",
        "tool",
        "install",
        "mng",
        "--reinstall",
        "--with",
        "coolname",
    )


def test_build_uv_tool_install_remove_last_dep() -> None:
    """build_uv_tool_install_remove should work when removing the only extra."""
    base = ToolRequirement(name="mng")
    existing = [ToolRequirement(name="mng-opencode")]
    cmd = build_uv_tool_install_remove(base, existing, "mng-opencode")
    assert cmd == ("uv", "tool", "install", "mng", "--reinstall")
