import argparse
import logging
import socket
import sys
import webbrowser
from pathlib import Path

import uvicorn

from .server import create_app


def find_transcript_by_session_id(session_id: str) -> Path | None:
    """Find transcript file for given session ID by searching ~/.claude/projects/."""
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    # Search all project directories for the session
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            transcript = project_dir / f"{session_id}.jsonl"
            if transcript.exists():
                return transcript

    return None


def find_free_port() -> int:
    """Find an available port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Web viewer for Claude Code sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  claude_web_view --session-id abc123def456
  claude_web_view --transcript ~/.claude/projects/my-project/session.jsonl
  claude_web_view --transcript session.jsonl --theme dark --port 8080
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--session-id",
        help="Claude Code session UUID to view",
    )
    group.add_argument(
        "--transcript",
        type=Path,
        help="Path to transcript JSONL file",
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Port to serve on (default: auto-select)",
    )
    parser.add_argument(
        "--theme",
        choices=["light", "dark", "system"],
        default="system",
        help="UI theme (default: system)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically",
    )

    args = parser.parse_args()

    # Resolve transcript path
    transcript_path: Path
    if args.session_id:
        found_path = find_transcript_by_session_id(args.session_id)
        if found_path is None:
            print(f"Error: No transcript found for session {args.session_id}", file=sys.stderr)
            print("Searched in ~/.claude/projects/*/", file=sys.stderr)
            sys.exit(1)
        assert found_path is not None  # type narrowing for ty
        transcript_path = found_path
    else:
        assert args.transcript is not None  # mutually exclusive required group
        transcript_path = args.transcript.expanduser().resolve()
        if not transcript_path.exists():
            print(f"Error: Transcript file not found: {transcript_path}", file=sys.stderr)
            sys.exit(1)

    port = args.port or find_free_port()

    # Create app with configuration
    app = create_app(
        transcript_path=transcript_path,
        theme=args.theme,
    )

    url = f"http://localhost:{port}"
    print(f"claude_web_view starting at {url}")

    if not args.no_browser:
        # Open browser after a short delay to let server start
        import threading

        def open_browser() -> None:
            import time

            time.sleep(0.5)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    # Suppress noisy shutdown logs
    logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="critical",
        access_log=False,
        timeout_graceful_shutdown=1,  # Don't wait long for SSE connections to close
    )


if __name__ == "__main__":
    main()
