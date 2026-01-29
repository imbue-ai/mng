#!/usr/bin/env python3
"""Terminate a Modal sandbox."""
import sys

import modal


def main():
    if len(sys.argv) < 2:
        print("Usage: modal-destroy.py <sandbox_id>", file=sys.stderr)
        sys.exit(1)

    sandbox_id = sys.argv[1]

    sandbox = modal.Sandbox.from_id(sandbox_id)
    sandbox.terminate()
    print(f"Terminated sandbox {sandbox_id}")


if __name__ == "__main__":
    main()
