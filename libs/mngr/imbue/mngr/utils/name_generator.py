from functools import cache
from pathlib import Path

from coolname import RandomGenerator

from imbue.imbue_common.pure import pure
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentNameStyle
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostNameStyle


@pure
def _get_resources_path() -> Path:
    """Get the path to the resources directory."""
    return Path(__file__).parent.parent / "resources" / "data" / "name_lists"


def _load_wordlist(category: str, style: str) -> list[list[str]]:
    """Load a wordlist from a txt file.

    Returns words wrapped in single-item lists because coolname expects each
    word to be a list of parts that get joined. Without this wrapping, coolname
    treats each character as a separate part and joins them with hyphens.
    """
    wordlist_path = _get_resources_path() / category / f"{style}.txt"
    words: list[list[str]] = []
    for line in wordlist_path.read_text().splitlines():
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith("#"):
            words.append([stripped_line])
    return words


@cache
def _get_agent_generator(style: AgentNameStyle) -> RandomGenerator:
    """Get a cached RandomGenerator for the given agent name style."""
    style_name = style.value.lower()
    words = _load_wordlist("agent", style_name)
    config = {
        "all": {
            "type": "words",
            "words": words,
        },
    }
    return RandomGenerator(config)


@cache
def _get_host_generator(style: HostNameStyle) -> RandomGenerator:
    """Get a cached RandomGenerator for the given host name style."""
    style_name = style.value.lower()
    words = _load_wordlist("host", style_name)
    config = {
        "all": {
            "type": "words",
            "words": words,
        },
    }
    return RandomGenerator(config)


def generate_agent_name(style: AgentNameStyle) -> AgentName:
    """Generate a random agent name based on the specified style."""
    generator = _get_agent_generator(style)
    name = generator.generate_slug()
    return AgentName(name)


def generate_host_name(style: HostNameStyle) -> HostName:
    """Generate a random host name based on the specified style."""
    generator = _get_host_generator(style)
    name = generator.generate_slug()
    return HostName(name)
