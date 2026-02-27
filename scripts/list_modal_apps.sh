#!/usr/bin/env bash
# List all modal apps across all environments in a clean format
# Usage: bash scripts/list_modal_apps.sh

set -euo pipefail

ENVS=$(uv run modal environment list --json 2>/dev/null | python3 -c "
import sys, json
envs = json.load(sys.stdin)
for e in envs:
    print(e['name'])
")

for env in $ENVS; do
    apps_json=$(uv run modal app list --env "$env" --json 2>/dev/null || echo "[]")
    app_count=$(echo "$apps_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
    if [ "$app_count" -gt 0 ]; then
        echo "$apps_json" | python3 -c "
import sys, json
env = '$env'
apps = json.load(sys.stdin)
for app in apps:
    print(f'{env}\t{app[\"App ID\"]}\t{app[\"Description\"]}\t{app[\"State\"]}\t{app[\"Created at\"]}\t{app.get(\"Stopped at\", \"\")}')
"
    fi
done
