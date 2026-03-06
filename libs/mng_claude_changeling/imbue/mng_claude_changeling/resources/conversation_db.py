#!/usr/bin/env python3
"""Helper for chat.sh to interact with the changeling_conversations table.

Provides subcommands for CRUD operations on the changeling_conversations
table in the llm sqlite database, using parameterized queries for safety.

The table schema matches CHANGELING_CONVERSATIONS_TABLE_SQL from provisioning.py.
The table is expected to already exist (created during provisioning). If it
does not, the insert subcommand creates it as a safety net.

Usage:
    python3 conversation_db.py insert <db_path> <conversation_id> <model> <tags_json> <created_at>
    python3 conversation_db.py lookup-model <db_path> <conversation_id>
    python3 conversation_db.py count <db_path>
    python3 conversation_db.py max-rowid <db_path>
    python3 conversation_db.py poll-new <db_path> <max_rowid>

Environment: None required (all paths passed as arguments).
"""

import sqlite3
import sys

_CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS changeling_conversations ("
    "conversation_id TEXT PRIMARY KEY, "
    "model TEXT NOT NULL, "
    "tags TEXT NOT NULL DEFAULT '{}', "
    "created_at TEXT NOT NULL)"
)


def _insert(db_path: str, conversation_id: str, model: str, tags: str, created_at: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO changeling_conversations "
            "(conversation_id, model, tags, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, model, tags, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def _lookup_model(db_path: str, conversation_id: str) -> None:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT model FROM changeling_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row:
                print(row[0])
        finally:
            conn.close()
    except sqlite3.Error as e:
        print(f"WARNING: lookup-model failed: {e}", file=sys.stderr)


def _count(db_path: str) -> None:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT count(*) FROM changeling_conversations").fetchone()
            print(row[0] if row else 0)
        finally:
            conn.close()
    except sqlite3.Error:
        print(0)


def _max_rowid(db_path: str) -> None:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM conversations").fetchone()
            print(row[0] if row else 0)
        finally:
            conn.close()
    except sqlite3.Error:
        print(0)


def _poll_new(db_path: str, max_rowid: str) -> None:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT id FROM conversations WHERE rowid > ? ORDER BY rowid ASC LIMIT 1",
                (int(max_rowid),),
            ).fetchone()
            if row:
                print(row[0])
        finally:
            conn.close()
    except sqlite3.Error as e:
        print(f"WARNING: poll-new failed: {e}", file=sys.stderr)


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <subcommand> <db_path> [args...]", file=sys.stderr)
        sys.exit(1)

    subcommand = sys.argv[1]
    db_path = sys.argv[2]

    match subcommand:
        case "insert":
            _insert(db_path, sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
        case "lookup-model":
            _lookup_model(db_path, sys.argv[3])
        case "count":
            _count(db_path)
        case "max-rowid":
            _max_rowid(db_path)
        case "poll-new":
            _poll_new(db_path, sys.argv[3])
        case _ as unreachable:
            print(f"Unknown subcommand: {unreachable}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
