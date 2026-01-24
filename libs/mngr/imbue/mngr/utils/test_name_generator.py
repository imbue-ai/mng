"""Integration tests for the name generator module."""

from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentNameStyle
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostNameStyle
from imbue.mngr.utils.name_generator import _get_agent_generator
from imbue.mngr.utils.name_generator import _get_host_generator
from imbue.mngr.utils.name_generator import _get_resources_path
from imbue.mngr.utils.name_generator import _load_wordlist
from imbue.mngr.utils.name_generator import generate_agent_name
from imbue.mngr.utils.name_generator import generate_host_name


def test_get_resources_path_returns_valid_path() -> None:
    """Test that _get_resources_path returns a path to name_lists directory."""
    resources_path = _get_resources_path()

    assert resources_path.exists()
    assert resources_path.name == "name_lists"
    assert (resources_path / "agent").exists()
    assert (resources_path / "host").exists()


def test_load_wordlist_for_agent_english() -> None:
    """Test loading agent wordlist for English style."""
    words = _load_wordlist("agent", "english")

    assert len(words) > 0
    # Each word should be a list with a single string (coolname format)
    for word in words:
        assert isinstance(word, list)
        assert len(word) == 1
        assert isinstance(word[0], str)
        assert len(word[0]) > 0


def test_load_wordlist_for_agent_fantasy() -> None:
    """Test loading agent wordlist for fantasy style."""
    words = _load_wordlist("agent", "fantasy")

    assert len(words) > 0
    for word in words:
        assert isinstance(word, list)
        assert len(word) == 1


def test_load_wordlist_for_agent_scifi() -> None:
    """Test loading agent wordlist for scifi style."""
    words = _load_wordlist("agent", "scifi")

    assert len(words) > 0


def test_load_wordlist_for_agent_painters() -> None:
    """Test loading agent wordlist for painters style."""
    words = _load_wordlist("agent", "painters")

    assert len(words) > 0


def test_load_wordlist_for_agent_authors() -> None:
    """Test loading agent wordlist for authors style."""
    words = _load_wordlist("agent", "authors")

    assert len(words) > 0


def test_load_wordlist_for_agent_artists() -> None:
    """Test loading agent wordlist for artists style."""
    words = _load_wordlist("agent", "artists")

    assert len(words) > 0


def test_load_wordlist_for_agent_musicians() -> None:
    """Test loading agent wordlist for musicians style."""
    words = _load_wordlist("agent", "musicians")

    assert len(words) > 0


def test_load_wordlist_for_agent_animals() -> None:
    """Test loading agent wordlist for animals style."""
    words = _load_wordlist("agent", "animals")

    assert len(words) > 0


def test_load_wordlist_for_agent_scientists() -> None:
    """Test loading agent wordlist for scientists style."""
    words = _load_wordlist("agent", "scientists")

    assert len(words) > 0


def test_load_wordlist_for_agent_demons() -> None:
    """Test loading agent wordlist for demons style."""
    words = _load_wordlist("agent", "demons")

    assert len(words) > 0


def test_load_wordlist_for_host_astronomy() -> None:
    """Test loading host wordlist for astronomy style."""
    words = _load_wordlist("host", "astronomy")

    assert len(words) > 0


def test_load_wordlist_for_host_places() -> None:
    """Test loading host wordlist for places style."""
    words = _load_wordlist("host", "places")

    assert len(words) > 0


def test_load_wordlist_for_host_cities() -> None:
    """Test loading host wordlist for cities style."""
    words = _load_wordlist("host", "cities")

    assert len(words) > 0


def test_load_wordlist_for_host_fantasy() -> None:
    """Test loading host wordlist for fantasy style."""
    words = _load_wordlist("host", "fantasy")

    assert len(words) > 0


def test_load_wordlist_for_host_scifi() -> None:
    """Test loading host wordlist for scifi style."""
    words = _load_wordlist("host", "scifi")

    assert len(words) > 0


def test_load_wordlist_for_host_painters() -> None:
    """Test loading host wordlist for painters style."""
    words = _load_wordlist("host", "painters")

    assert len(words) > 0


def test_load_wordlist_for_host_authors() -> None:
    """Test loading host wordlist for authors style."""
    words = _load_wordlist("host", "authors")

    assert len(words) > 0


def test_load_wordlist_for_host_artists() -> None:
    """Test loading host wordlist for artists style."""
    words = _load_wordlist("host", "artists")

    assert len(words) > 0


def test_load_wordlist_for_host_musicians() -> None:
    """Test loading host wordlist for musicians style."""
    words = _load_wordlist("host", "musicians")

    assert len(words) > 0


def test_load_wordlist_for_host_scientists() -> None:
    """Test loading host wordlist for scientists style."""
    words = _load_wordlist("host", "scientists")

    assert len(words) > 0


def test_get_agent_generator_returns_generator() -> None:
    """Test that _get_agent_generator returns a RandomGenerator."""
    generator = _get_agent_generator(AgentNameStyle.ENGLISH)

    assert generator is not None
    # Generate a name to verify it works
    name = generator.generate_slug()
    assert isinstance(name, str)
    assert len(name) > 0


def test_get_agent_generator_is_cached() -> None:
    """Test that _get_agent_generator returns cached generators."""
    generator1 = _get_agent_generator(AgentNameStyle.FANTASY)
    generator2 = _get_agent_generator(AgentNameStyle.FANTASY)

    # Should be the same cached instance
    assert generator1 is generator2


def test_get_host_generator_returns_generator() -> None:
    """Test that _get_host_generator returns a RandomGenerator."""
    generator = _get_host_generator(HostNameStyle.ASTRONOMY)

    assert generator is not None
    name = generator.generate_slug()
    assert isinstance(name, str)
    assert len(name) > 0


def test_get_host_generator_is_cached() -> None:
    """Test that _get_host_generator returns cached generators."""
    generator1 = _get_host_generator(HostNameStyle.CITIES)
    generator2 = _get_host_generator(HostNameStyle.CITIES)

    assert generator1 is generator2


def test_generate_agent_name_english_returns_agent_name() -> None:
    """Test generating agent name with English style."""
    name = generate_agent_name(AgentNameStyle.ENGLISH)

    assert isinstance(name, AgentName)
    assert len(name) > 0


def test_generate_agent_name_fantasy_returns_agent_name() -> None:
    """Test generating agent name with fantasy style."""
    name = generate_agent_name(AgentNameStyle.FANTASY)

    assert isinstance(name, AgentName)
    assert len(name) > 0


def test_generate_agent_name_scifi_returns_agent_name() -> None:
    """Test generating agent name with scifi style."""
    name = generate_agent_name(AgentNameStyle.SCIFI)

    assert isinstance(name, AgentName)
    assert len(name) > 0


def test_generate_agent_name_painters_returns_agent_name() -> None:
    """Test generating agent name with painters style."""
    name = generate_agent_name(AgentNameStyle.PAINTERS)

    assert isinstance(name, AgentName)


def test_generate_agent_name_authors_returns_agent_name() -> None:
    """Test generating agent name with authors style."""
    name = generate_agent_name(AgentNameStyle.AUTHORS)

    assert isinstance(name, AgentName)


def test_generate_agent_name_artists_returns_agent_name() -> None:
    """Test generating agent name with artists style."""
    name = generate_agent_name(AgentNameStyle.ARTISTS)

    assert isinstance(name, AgentName)


def test_generate_agent_name_musicians_returns_agent_name() -> None:
    """Test generating agent name with musicians style."""
    name = generate_agent_name(AgentNameStyle.MUSICIANS)

    assert isinstance(name, AgentName)


def test_generate_agent_name_animals_returns_agent_name() -> None:
    """Test generating agent name with animals style."""
    name = generate_agent_name(AgentNameStyle.ANIMALS)

    assert isinstance(name, AgentName)


def test_generate_agent_name_scientists_returns_agent_name() -> None:
    """Test generating agent name with scientists style."""
    name = generate_agent_name(AgentNameStyle.SCIENTISTS)

    assert isinstance(name, AgentName)


def test_generate_agent_name_demons_returns_agent_name() -> None:
    """Test generating agent name with demons style."""
    name = generate_agent_name(AgentNameStyle.DEMONS)

    assert isinstance(name, AgentName)


def test_generate_host_name_astronomy_returns_host_name() -> None:
    """Test generating host name with astronomy style."""
    name = generate_host_name(HostNameStyle.ASTRONOMY)

    assert isinstance(name, HostName)
    assert len(name) > 0


def test_generate_host_name_places_returns_host_name() -> None:
    """Test generating host name with places style."""
    name = generate_host_name(HostNameStyle.PLACES)

    assert isinstance(name, HostName)


def test_generate_host_name_cities_returns_host_name() -> None:
    """Test generating host name with cities style."""
    name = generate_host_name(HostNameStyle.CITIES)

    assert isinstance(name, HostName)


def test_generate_host_name_fantasy_returns_host_name() -> None:
    """Test generating host name with fantasy style."""
    name = generate_host_name(HostNameStyle.FANTASY)

    assert isinstance(name, HostName)


def test_generate_host_name_scifi_returns_host_name() -> None:
    """Test generating host name with scifi style."""
    name = generate_host_name(HostNameStyle.SCIFI)

    assert isinstance(name, HostName)


def test_generate_host_name_painters_returns_host_name() -> None:
    """Test generating host name with painters style."""
    name = generate_host_name(HostNameStyle.PAINTERS)

    assert isinstance(name, HostName)


def test_generate_host_name_authors_returns_host_name() -> None:
    """Test generating host name with authors style."""
    name = generate_host_name(HostNameStyle.AUTHORS)

    assert isinstance(name, HostName)


def test_generate_host_name_artists_returns_host_name() -> None:
    """Test generating host name with artists style."""
    name = generate_host_name(HostNameStyle.ARTISTS)

    assert isinstance(name, HostName)


def test_generate_host_name_musicians_returns_host_name() -> None:
    """Test generating host name with musicians style."""
    name = generate_host_name(HostNameStyle.MUSICIANS)

    assert isinstance(name, HostName)


def test_generate_host_name_scientists_returns_host_name() -> None:
    """Test generating host name with scientists style."""
    name = generate_host_name(HostNameStyle.SCIENTISTS)

    assert isinstance(name, HostName)


def test_generate_agent_name_generates_unique_names() -> None:
    """Test that generate_agent_name generates unique names across multiple calls."""
    names = set()
    for _ in range(10):
        name = generate_agent_name(AgentNameStyle.ENGLISH)
        names.add(str(name))

    # With randomness, we expect most names to be unique
    # Allow for some duplicates due to randomness, but expect at least 5 unique names
    assert len(names) >= 5


def test_generate_host_name_generates_unique_names() -> None:
    """Test that generate_host_name generates unique names across multiple calls."""
    names = set()
    for _ in range(10):
        name = generate_host_name(HostNameStyle.ASTRONOMY)
        names.add(str(name))

    assert len(names) >= 5
