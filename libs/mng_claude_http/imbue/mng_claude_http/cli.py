import argparse
import sys

from imbue.mng_claude_http.primitives import HttpPort
from imbue.mng_claude_http.server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude Code HTTP interface")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Start the web server")
    serve_parser.add_argument("--port", type=int, default=3457, help="Port to listen on (default: 3457)")
    serve_parser.add_argument("--work-dir", type=str, default=None, help="Working directory for Claude Code")

    args = parser.parse_args()

    if args.command == "serve":
        port = HttpPort(args.port)
        print(f"Starting Claude HTTP server on http://127.0.0.1:{port}")
        run_server(port, args.work_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
