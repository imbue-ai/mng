import os
import signal
import sys

import llm.cli
import pytest
import sqlite_utils

from imbue.llm_live_chat.conftest import invoke_live_chat
from imbue.llm_live_chat.plugin import _insert_response

_HAS_SIGUSR1 = hasattr(signal, "SIGUSR1")


@pytest.mark.xfail(sys.platform == "win32", reason="Expected to fail on Windows")
def test_live_chat_basic(mock_model, logs_db, cli_runner):
    mock_model.enqueue(["one world"])
    mock_model.enqueue(["one again"])
    result = invoke_live_chat(cli_runner, "Hi\nHi two")
    assert result.exit_code == 0
    assert "Chatting with mock" in result.output
    assert "> Hi\none world\n" in result.output
    assert "> Hi two\none again\n" in result.output

    conversations = list(logs_db["conversations"].rows)
    assert len(conversations) == 1
    responses = list(logs_db["responses"].rows)
    assert len(responses) == 2
    assert responses[0]["prompt"] == "Hi"
    assert responses[0]["response"] == "one world"
    assert responses[1]["prompt"] == "Hi two"
    assert responses[1]["response"] == "one again"


@pytest.mark.xfail(sys.platform == "win32", reason="Expected to fail on Windows")
def test_live_chat_continue(mock_model, logs_db, cli_runner):
    mock_model.enqueue(["first"])
    invoke_live_chat(cli_runner, "Hi")

    mock_model.enqueue(["continued"])
    result = invoke_live_chat(cli_runner, "More", extra_args=["-c"])
    assert result.exit_code == 0
    assert "continued" in result.output

    responses = list(logs_db["responses"].rows)
    assert len(responses) == 2


@pytest.mark.skipif(not _HAS_SIGUSR1, reason="SIGUSR1 not available")
@pytest.mark.xfail(sys.platform == "win32", reason="Expected to fail on Windows")
def test_live_chat_sigusr1_pending(mock_model, logs_db, cli_runner):
    """SIGUSR1 during streaming sets _check_pending, displayed after streaming."""
    log_path = str(llm.cli.logs_db_path())
    call_count = [0]

    def execute_inject_and_signal(prompt, stream, response, conversation):
        call_count[0] += 1
        if call_count[0] == 1:
            yield "first reply"
            response.set_usage(input=1, output=1)
        elif call_count[0] == 2:
            conv_id = conversation.id
            db = sqlite_utils.Database(log_path)
            from llm.migrations import migrate
            from llm.utils import monotonic_ulid

            migrate(db)
            db["conversations"].insert(
                {"id": conv_id, "name": "test", "model": "mock"},
                ignore=True,
            )
            _insert_response(db, monotonic_ulid, "mock", "external prompt", "external followup message", conv_id)
            os.kill(os.getpid(), signal.SIGUSR1)
            yield "second reply"
            response.set_usage(input=1, output=1)

    mock_model.execute = execute_inject_and_signal

    result = invoke_live_chat(cli_runner, "Hello\nWorld")
    assert result.exit_code == 0
    assert "external followup message" in result.output
    assert "> external prompt" in result.output


def test_inject_into_conversation(mock_model, logs_db, cli_runner):
    mock_model.enqueue(["hello back"])
    invoke_live_chat(cli_runner, "Hi")

    conv_id = list(logs_db["conversations"].rows)[0]["id"]

    result = cli_runner.invoke(
        llm.cli.cli,
        ["inject", "followup from external", "--cid", conv_id, "--prompt", "system note"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "Injected message into conversation" in result.output

    responses = list(logs_db["responses"].rows_where("conversation_id = ?", [conv_id], order_by="datetime_utc"))
    assert len(responses) == 2
    injected = responses[1]
    assert injected["response"] == "followup from external"
    assert injected["prompt"] == "system note"
    assert injected["model"] == "mock"


def test_inject_without_cid_creates_new_conversation(mock_model, logs_db, cli_runner):
    """Inject without --cid always creates a new conversation."""
    mock_model.enqueue(["reply"])
    invoke_live_chat(cli_runner, "Hi")

    result = cli_runner.invoke(
        llm.cli.cli,
        ["inject", "new conv message"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    convs = list(logs_db["conversations"].rows)
    assert len(convs) == 2
    responses = list(logs_db["responses"].rows_where(select="response"))
    assert {"response": "new conv message"} in responses


def test_inject_no_conversations_creates_one(logs_db, cli_runner):
    """Inject with no existing conversations creates a new one."""
    result = cli_runner.invoke(
        llm.cli.cli,
        ["inject", "first message"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "Injected message into conversation" in result.output

    convs = list(logs_db["conversations"].rows)
    assert len(convs) == 1
    responses = list(logs_db["responses"].rows)
    assert len(responses) == 1
    assert responses[0]["response"] == "first message"
    assert responses[0]["conversation_id"] == convs[0]["id"]


def test_inject_bad_conversation_id(mock_model, logs_db, cli_runner):
    mock_model.enqueue(["reply"])
    invoke_live_chat(cli_runner, "Hi")

    result = cli_runner.invoke(llm.cli.cli, ["inject", "msg", "--cid", "nonexistent-id"])
    assert result.exit_code != 0
    assert "No conversation found" in result.output


@pytest.mark.xfail(sys.platform == "win32", reason="Expected to fail on Windows")
def test_show_history(mock_model, logs_db, cli_runner):
    mock_model.enqueue(["first response"])
    mock_model.enqueue(["second response"])
    invoke_live_chat(cli_runner, "Hello\nWorld")

    mock_model.enqueue(["third response"])
    result = invoke_live_chat(cli_runner, "More", extra_args=["-c", "--show-history"])
    assert result.exit_code == 0
    assert "> Hello" in result.output
    assert "first response" in result.output
    assert "> World" in result.output
    assert "second response" in result.output
    assert "third response" in result.output


@pytest.mark.xfail(sys.platform == "win32", reason="Expected to fail on Windows")
def test_show_history_with_injected(mock_model, logs_db, cli_runner):
    mock_model.enqueue(["reply"])
    invoke_live_chat(cli_runner, "Hi")

    conv_id = list(logs_db["conversations"].rows)[0]["id"]

    cli_runner.invoke(
        llm.cli.cli,
        ["inject", "injected followup", "--cid", conv_id, "--prompt", "Agent"],
        catch_exceptions=False,
    )

    mock_model.enqueue(["new reply"])
    result = invoke_live_chat(cli_runner, "Next", extra_args=["-c", "--show-history"])
    assert result.exit_code == 0
    assert "> Hi" in result.output
    assert "reply" in result.output
    assert "> Agent" in result.output
    assert "injected followup" in result.output
