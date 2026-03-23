#!/bin/bash
set -euo pipefail
# Load Modal credentials from env vars or ~/.modal.toml.
# Source this script to set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET.
if [[ -z "${MODAL_TOKEN_ID:-}" || -z "${MODAL_TOKEN_SECRET:-}" ]]; then
    eval "$(uv run python -c "
import tomllib, pathlib
p = pathlib.Path.home() / '.modal.toml'
if p.exists():
    for v in tomllib.loads(p.read_text()).values():
        if v.get('active'):
            print(f'export MODAL_TOKEN_ID={v[\"token_id\"]}')
            print(f'export MODAL_TOKEN_SECRET={v[\"token_secret\"]}')
            break
")"
fi
