#!/usr/bin/env bash
#
# Converts a raw GitHub URL to a tokenized URL that works in browsers.
#
# Usage: ./get_metadata_url.sh <raw_url>

set -euo pipefail

URL="$1"

# Parse: https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
if [[ "$URL" =~ raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
    REF="${BASH_REMATCH[3]}"
    FILE_PATH="${BASH_REMATCH[4]}"
else
    echo "ERROR: Could not parse URL" >&2
    exit 1
fi

gh api "repos/${OWNER}/${REPO}/contents/${FILE_PATH}?ref=${REF}" --jq '.download_url'
