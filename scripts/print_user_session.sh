#!/bin/bash
# Print out a Claude Code conversation history in a way that is easier to read and analyze

set -euo pipefail

cat `find ~/.claude/projects/ -name "$CLAUDE_SESSION_ID.jsonl"` | \
  grep -v "tool_use_id" | \
  grep -v 'content":"<' | \
  grep -v '"type":"progress"' | \
  grep -v '"type":"thinking"' | \
  grep -v '"type":"tool_use"' | \
  grep -v '"type":"system"' | \
  grep user | \
  jq '{type: .type, content:  .message.content}' | \
  jq -s 'reduce .[] as $msg ([]; if length > 0 and .[-1].type == "assistant" and $msg.type == "assistant" then .[-1].content[0].text += "\n\n" + $msg.content[0].text else . + [$msg] end)'
