#!/bin/bash
# Print out Claude Code conversation history in a way that is easier to read and analyze.
# Prints all sessions in chronological order, filtered to show only user/assistant messages.
#
# Uses `mngr transcript` to retrieve the raw JSONL, then filters and formats it.

set -euo pipefail

_AGENT_NAME="${MNGR_AGENT_NAME:-${1:-}}"

if [ -z "$_AGENT_NAME" ]; then
    echo "Usage: print_user_session.sh [agent-name]" >&2
    echo "Or set MNGR_AGENT_NAME environment variable" >&2
    exit 1
fi

uv run mngr transcript "$_AGENT_NAME" | \
  grep -v "tool_use_id" | \
  grep -v 'content":"<' | \
  grep -v '"type":"progress"' | \
  grep -v '"type":"thinking"' | \
  grep -v '"type":"tool_use"' | \
  grep -v '"type":"system"' | \
  grep user | \
  jq '{type: .type, content:  .message.content}' | \
  jq -s 'reduce .[] as $msg ([]; if length > 0 and .[-1].type == "assistant" and $msg.type == "assistant" then .[-1].content[0].text += "\n\n" + $msg.content[0].text else . + [$msg] end)'
