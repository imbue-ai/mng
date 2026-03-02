from io import StringIO

from dotenv import dotenv_values

from imbue.imbue_common.pure import pure


@pure
def parse_env_file(content: str) -> dict[str, str]:
    """Parse an environment file into a dict."""
    raw = dotenv_values(stream=StringIO(content))
    return {k: v for k, v in raw.items() if v is not None}
