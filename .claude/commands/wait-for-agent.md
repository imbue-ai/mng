---
argument-hint: [agent_name] [post_wait_instructions]
description: Wait for another agent to enter WAITING state, then execute follow-up instructions
allowed-tools: Bash(uv run mng list *), Bash(while true; do*)
---

Your task is to wait for agent "$1" to finish its current work (enter the WAITING state), then do the following: $2

## Current Agent States

!`uv run mng list --format '{name}: {state}' 2>/dev/null`

## Polling Procedure

Find agent "$1" in the list above.

If the agent is not listed, it does not exist. Report the error and stop.

If the agent is already in WAITING, DONE, or STOPPED state, skip the polling loop and proceed directly to the follow-up task.

Otherwise, poll the agent's lifecycle state every 60 seconds until it leaves the RUNNING state. Run the following bash command (with a 600000ms timeout):

```bash
while true; do
  STATE=$(uv run mng list --include 'name == "$1"' --format '{state}' 2>/dev/null | head -1)
  echo "[$(date '+%H:%M:%S')] Agent '$1' state: ${STATE:-NOT_FOUND}"
  case "$STATE" in
    WAITING|DONE|STOPPED) echo "Agent '$1' is ready (state: $STATE)"; break ;;
    "") echo "Agent '$1' not found, stopping"; break ;;
    *) sleep 60 ;;
  esac
done
```

If this command times out (after 10 minutes), simply re-run the same command. Continue re-running until the agent reaches a terminal state.

## After the Agent is Ready

Once the agent is in WAITING, DONE, or STOPPED state, proceed with the follow-up task: $2
