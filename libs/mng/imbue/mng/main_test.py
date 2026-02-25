"""Unit tests for plugin manager helpers in main.py."""

from types import ModuleType

import pluggy

from imbue.mng.main import _unregister_disabled_by_default_plugins
from imbue.mng.plugins import hookspecs


def _make_pm_with_plugins(
    plugins: list[tuple[str, ModuleType]],
) -> pluggy.PluginManager:
    """Create a plugin manager and register the given (name, module) pairs."""
    pm = pluggy.PluginManager("mng")
    pm.add_hookspecs(hookspecs)
    for name, module in plugins:
        pm.register(module, name=name)
    return pm


def _make_plugin_module(*, enabled_by_default: bool | None = None) -> ModuleType:
    """Create a fake plugin module, optionally with ENABLED_BY_DEFAULT."""
    mod = ModuleType("fake_plugin")
    if enabled_by_default is not None:
        mod.ENABLED_BY_DEFAULT = enabled_by_default  # type: ignore[attr-defined]
    return mod


def _registered_names(pm: pluggy.PluginManager) -> set[str]:
    return {name for name, _ in pm.list_name_plugin() if name is not None and not name.startswith("_")}


def test_unregister_removes_disabled_by_default() -> None:
    """Plugins with ENABLED_BY_DEFAULT=False are unregistered."""
    disabled_mod = _make_plugin_module(enabled_by_default=False)
    pm = _make_pm_with_plugins([("my_plugin", disabled_mod)])

    _unregister_disabled_by_default_plugins(pm, frozenset())

    assert "my_plugin" not in _registered_names(pm)


def test_unregister_keeps_enabled_by_default() -> None:
    """Plugins with ENABLED_BY_DEFAULT=True are kept."""
    enabled_mod = _make_plugin_module(enabled_by_default=True)
    pm = _make_pm_with_plugins([("my_plugin", enabled_mod)])

    _unregister_disabled_by_default_plugins(pm, frozenset())

    assert "my_plugin" in _registered_names(pm)


def test_unregister_keeps_plugin_without_attribute() -> None:
    """Plugins without ENABLED_BY_DEFAULT attribute default to enabled."""
    mod = _make_plugin_module()
    pm = _make_pm_with_plugins([("my_plugin", mod)])

    _unregister_disabled_by_default_plugins(pm, frozenset())

    assert "my_plugin" in _registered_names(pm)


def test_unregister_keeps_disabled_by_default_if_explicitly_enabled() -> None:
    """Plugins with ENABLED_BY_DEFAULT=False are kept if explicitly enabled."""
    disabled_mod = _make_plugin_module(enabled_by_default=False)
    pm = _make_pm_with_plugins([("my_plugin", disabled_mod)])

    _unregister_disabled_by_default_plugins(pm, frozenset({"my_plugin"}))

    assert "my_plugin" in _registered_names(pm)


def test_unregister_mixed_plugins() -> None:
    """Only disabled-by-default plugins without explicit enable are removed."""
    enabled_mod = _make_plugin_module(enabled_by_default=True)
    disabled_mod = _make_plugin_module(enabled_by_default=False)
    disabled_but_enabled_mod = _make_plugin_module(enabled_by_default=False)
    no_attr_mod = _make_plugin_module()

    pm = _make_pm_with_plugins(
        [
            ("enabled", enabled_mod),
            ("disabled", disabled_mod),
            ("disabled_but_enabled", disabled_but_enabled_mod),
            ("no_attr", no_attr_mod),
        ]
    )

    _unregister_disabled_by_default_plugins(pm, frozenset({"disabled_but_enabled"}))

    names = _registered_names(pm)
    assert "enabled" in names
    assert "disabled" not in names
    assert "disabled_but_enabled" in names
    assert "no_attr" in names
