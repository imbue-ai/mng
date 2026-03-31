"""Tests for the injected-message watcher plugin."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from imbue.mngr_llm.resources.webchat_injected_messages import _get_max_rowid
from imbue.mngr_llm.resources.webchat_injected_messages import _get_tracked_conversation_ids
from imbue.mngr_llm.resources.webchat_injected_messages import _is_injected_response
from imbue.mngr_llm.resources.webchat_injected_messages import _poll_for_injected_messages
from imbue.mngr_llm.resources.webchat_injected_messages import _run_poll_loop


def _create_test_db(db_path: Path) -> None:
    """Create a minimal llm database with the required tables."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, name TEXT, model TEXT)")
    conn.execute(
        "CREATE TABLE responses ("
        "id TEXT PRIMARY KEY, model TEXT, prompt TEXT, system TEXT, "
        "prompt_json TEXT, options_json TEXT, response TEXT, response_json TEXT, "
        "conversation_id TEXT, duration_ms INTEGER, datetime_utc TEXT)"
    )
    conn.execute(
        "CREATE TABLE mind_conversations ("
        "conversation_id TEXT PRIMARY KEY, tags TEXT NOT NULL DEFAULT '{}', "
        "created_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()


def _insert_conversation(db_path: Path, conversation_id: str, name: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO conversations (id, name, model) VALUES (?, ?, ?)",
        (conversation_id, name, "test-model"),
    )
    conn.execute(
        "INSERT INTO mind_conversations (conversation_id, tags, created_at) VALUES (?, ?, ?)",
        (conversation_id, '{"name":"' + name + '"}', "2025-01-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()


def _insert_response(
    db_path: Path,
    response_id: str,
    conversation_id: str,
    prompt: str,
    response: str,
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO responses (id, conversation_id, prompt, response, datetime_utc) "
        "VALUES (?, ?, ?, ?, ?)",
        (response_id, conversation_id, prompt, response, "2025-01-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()


# -- _is_injected_response tests --


def test_injected_with_empty_prompt_and_response() -> None:
    assert _is_injected_response("", "Hello world") is True


def test_injected_with_dots_prompt() -> None:
    assert _is_injected_response("...", "Hello world") is True


def test_injected_with_none_prompt() -> None:
    assert _is_injected_response(None, "Hello world") is True


def test_not_injected_with_real_prompt() -> None:
    assert _is_injected_response("What is the weather?", "It's sunny.") is False


def test_not_injected_with_empty_response() -> None:
    assert _is_injected_response("", "") is False


def test_not_injected_with_whitespace_response() -> None:
    assert _is_injected_response("", "   ") is False


def test_not_injected_preliminary_row() -> None:
    """Preliminary rows from llm live-chat have prompt set and response empty."""
    assert _is_injected_response("user message", "") is False


# -- _get_max_rowid tests --


def test_get_max_rowid_returns_zero_for_missing_db(tmp_path: Path) -> None:
    assert _get_max_rowid(tmp_path / "nonexistent.db") == 0


def test_get_max_rowid_returns_zero_for_empty_table(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    assert _get_max_rowid(db_path) == 0


def test_get_max_rowid_returns_correct_value(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "hello", "world")
    _insert_response(db_path, "resp-2", "conv-1", "foo", "bar")
    assert _get_max_rowid(db_path) == 2


# -- _get_tracked_conversation_ids tests --


def test_get_tracked_conversation_ids_returns_empty_for_missing_db(tmp_path: Path) -> None:
    assert _get_tracked_conversation_ids(tmp_path / "nonexistent.db") == set()


def test_get_tracked_conversation_ids_returns_correct_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Chat 1")
    _insert_conversation(db_path, "conv-2", "Chat 2")
    assert _get_tracked_conversation_ids(db_path) == {"conv-1", "conv-2"}


# -- _poll_for_injected_messages tests --


def test_poll_returns_empty_for_missing_db(tmp_path: Path) -> None:
    results, max_rowid = _poll_for_injected_messages(tmp_path / "nonexistent.db", 0, {"conv-1"})
    assert results == []
    assert max_rowid == 0


def test_poll_detects_injected_message_with_empty_prompt(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "", "injected content")

    results, max_rowid = _poll_for_injected_messages(db_path, 0, {"conv-1"})
    assert results == ["conv-1"]
    assert max_rowid == 1


def test_poll_detects_injected_message_with_dots_prompt(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "...", "agent injected content")

    results, max_rowid = _poll_for_injected_messages(db_path, 0, {"conv-1"})
    assert results == ["conv-1"]
    assert max_rowid == 1


def test_poll_ignores_normal_prompt_response(tmp_path: Path) -> None:
    """Normal llm prompt responses have a non-empty user prompt."""
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "What is 2+2?", "4")

    results, max_rowid = _poll_for_injected_messages(db_path, 0, {"conv-1"})
    assert results == []
    assert max_rowid == 1


def test_poll_ignores_preliminary_rows(tmp_path: Path) -> None:
    """Preliminary rows from llm live-chat have prompt set and response empty."""
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "user msg", "")

    results, max_rowid = _poll_for_injected_messages(db_path, 0, {"conv-1"})
    assert results == []
    assert max_rowid == 1


def test_poll_skips_untracked_conversations(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "", "injected")

    results, max_rowid = _poll_for_injected_messages(db_path, 0, {"conv-other"})
    assert results == []
    assert max_rowid == 1


def test_poll_only_returns_messages_after_rowid(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "", "old injected")
    _insert_response(db_path, "resp-2", "conv-1", "", "new injected")

    results, max_rowid = _poll_for_injected_messages(db_path, 1, {"conv-1"})
    assert results == ["conv-1"]
    assert max_rowid == 2


def test_poll_deduplicates_conversation_ids(tmp_path: Path) -> None:
    """Multiple injected messages in the same conversation produce one notification."""
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")
    _insert_response(db_path, "resp-1", "conv-1", "", "first injected")
    _insert_response(db_path, "resp-2", "conv-1", "", "second injected")

    results, max_rowid = _poll_for_injected_messages(db_path, 0, {"conv-1"})
    assert results == ["conv-1"]
    assert max_rowid == 2


# -- _run_poll_loop tests --


def test_poll_loop_does_not_broadcast_for_normal_messages(tmp_path: Path) -> None:
    db_path = tmp_path / "logs.db"
    _create_test_db(db_path)
    _insert_conversation(db_path, "conv-1", "Test")

    received_calls: list[tuple[str, dict[str, Any]]] = []

    def tracking_broadcaster(conversation_id: str, event: dict[str, Any]) -> None:
        received_calls.append((conversation_id, event))

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_poll_loop,
        args=(db_path, tracking_broadcaster, stop_event),
        daemon=True,
    )
    thread.start()

    # Insert a normal message (non-empty prompt)
    _insert_response(db_path, "resp-1", "conv-1", "What is 2+2?", "4")

    # Wait two poll cycles
    poll_done = threading.Event()
    poll_done.wait(timeout=5.0)
    stop_event.set()
    thread.join(timeout=5.0)

    assert len(received_calls) == 0
