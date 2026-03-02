#!/bin/bash
# Handler for the chat ttyd (invoked by ttyd --url-arg).
#
# When accessed with ?arg=<conversation_id>, resumes that conversation.
# When accessed with no args, starts a new conversation.
#
# Environment:
#   MNG_HOST_DIR  - host data directory (contains commands/chat.sh)

set -euo pipefail

CHAT_SCRIPT="${MNG_HOST_DIR:?MNG_HOST_DIR must be set}/commands/chat.sh"

if [ -n "${1:-}" ]; then
    exec "$CHAT_SCRIPT" --resume "$1"
else
    exec "$CHAT_SCRIPT" --new
fi
