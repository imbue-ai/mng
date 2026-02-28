import sys

# Must be set before any llm imports to prevent all entry-point plugins
# from being loaded, matching the behavior of the llm test suite.
sys._called_from_test = True  # type: ignore[attr-defined]

from collections.abc import Iterable
from collections.abc import Iterator
from typing import Optional

import llm
import llm.cli
import pytest
import sqlite_utils
from llm.plugins import pm
from pydantic import Field

import imbue.llm_live_chat.plugin as llm_live_chat_plugin


class MockModel(llm.Model):
    model_id = "mock"
    attachment_types = {"image/png", "audio/wav"}
    supports_schema = True
    supports_tools = True

    class Options(llm.Options):
        max_tokens: Optional[int] = Field(description="Maximum number of tokens to generate.", default=None)

    def __init__(self):
        self.history = []
        self._queue = []
        self.resolved_model_name = None

    def enqueue(self, messages):
        assert isinstance(messages, list)
        self._queue.append(messages)

    def execute(self, prompt, stream, response, conversation):
        self.history.append((prompt, stream, response, conversation))
        gathered = []
        while True:
            try:
                messages = self._queue.pop(0)
                for message in messages:
                    gathered.append(message)
                    yield message
                break
            except IndexError:
                break
        response.set_usage(input=len((prompt.prompt or "").split()), output=len(gathered))
        if self.resolved_model_name is not None:
            response.set_resolved_model(self.resolved_model_name)


class AsyncMockModel(llm.AsyncModel):
    model_id = "mock"
    supports_schema = True

    def __init__(self):
        self.history = []
        self._queue = []
        self.resolved_model_name = None

    def enqueue(self, messages):
        assert isinstance(messages, list)
        self._queue.append(messages)

    async def execute(self, prompt, stream, response, conversation):
        self.history.append((prompt, stream, response, conversation))
        gathered = []
        while True:
            try:
                messages = self._queue.pop(0)
                for message in messages:
                    gathered.append(message)
                    yield message
                break
            except IndexError:
                break
        response.set_usage(input=len((prompt.prompt or "").split()), output=len(gathered))
        if self.resolved_model_name is not None:
            response.set_resolved_model(self.resolved_model_name)


class EmbedDemo(llm.EmbeddingModel):
    model_id = "embed-demo"
    batch_size = 10
    supports_binary = True

    def __init__(self):
        self.embedded_content = []

    def embed_batch(self, items: Iterable[str | bytes]) -> Iterator[list[float]]:
        if not hasattr(self, "batch_count"):
            self.batch_count = 0
        self.batch_count += 1
        for item in items:
            self.embedded_content.append(item)
            text = item if isinstance(item, str) else item.decode("utf-8", errors="replace")
            words = text.split()[:16]
            embedding = [float(len(word)) for word in words]
            embedding += [0.0] * (16 - len(embedding))
            yield embedding


@pytest.fixture
def user_path(tmpdir):
    dir = tmpdir / "llm.datasette.io"
    dir.mkdir()
    return dir


@pytest.fixture
def logs_db(user_path):
    return sqlite_utils.Database(str(user_path / "logs.db"))


@pytest.fixture(autouse=True)
def env_setup(monkeypatch, user_path):
    monkeypatch.setenv("LLM_USER_PATH", str(user_path))


@pytest.fixture
def embed_demo():
    return EmbedDemo()


@pytest.fixture
def mock_model():
    return MockModel()


@pytest.fixture
def async_mock_model():
    return AsyncMockModel()


@pytest.fixture(autouse=True)
def register_mock_models(embed_demo, mock_model, async_mock_model):
    class MockModelsPlugin:
        __name__ = "MockModelsPlugin"

        @llm.hookimpl
        def register_embedding_models(self, register):
            register(embed_demo)

        @llm.hookimpl
        def register_models(self, register):
            register(mock_model, async_model=async_mock_model)

    pm.register(MockModelsPlugin(), name="undo-mock-models-plugin")
    try:
        yield
    finally:
        pm.unregister(name="undo-mock-models-plugin")


@pytest.fixture(autouse=True)
def register_live_chat_plugin():
    if not pm.is_registered(llm_live_chat_plugin):
        pm.register(llm_live_chat_plugin, name="undo-llm-live-chat")
    # The register_commands hook already fired during llm.cli import,
    # so we must call it manually for our plugin.
    if "live-chat" not in llm.cli.cli.commands:
        llm_live_chat_plugin.register_commands(llm.cli.cli)
    yield


@pytest.fixture
def cli_runner():
    from click.testing import CliRunner

    return CliRunner()


def invoke_live_chat(cli_runner, user_input, extra_args=None):
    """Invoke 'llm live-chat -m mock' with the given input, appending 'quit' automatically."""
    args = ["live-chat", "-m", "mock"] + (extra_args or [])
    return cli_runner.invoke(
        llm.cli.cli,
        args,
        input=user_input + "\nquit\n",
        catch_exceptions=False,
    )
