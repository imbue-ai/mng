from imbue.imbue_common.pure import pure


# FIXME: this is a silly way of parsing env files - we should use a proper library for this so that quotes, etc are handled correctly
@pure
def parse_env_file(content: str) -> dict[str, str]:
    """Parse an environment file into a dict."""
    env: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            else:
                # Unquoted value - use as-is
                pass
            env[key.strip()] = value
    return env
