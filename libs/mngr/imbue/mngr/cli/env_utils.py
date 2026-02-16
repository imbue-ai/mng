import os

from imbue.mngr.config.data_types import EnvVar


def resolve_env_vars(
    pass_env_var_names: tuple[str, ...],
    explicit_env_var_strings: tuple[str, ...],
) -> tuple[EnvVar, ...]:
    """Resolve and merge environment variables.

    Resolves pass_env_var_names from os.environ and merges with explicit_env_var_strings.
    Explicit env vars take precedence over pass-through values.
    """
    # Start with pass-through env vars from current shell
    merged: dict[str, str] = {}
    for var_name in pass_env_var_names:
        if var_name in os.environ:
            merged[var_name] = os.environ[var_name]

    # Explicit env vars override pass-through values
    for env_str in explicit_env_var_strings:
        env_var = EnvVar.from_string(env_str)
        merged[env_var.key] = env_var.value

    return tuple(EnvVar(key=k, value=v) for k, v in merged.items())
