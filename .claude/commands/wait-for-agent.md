---
argument-hint: [agent_name] [instructions]
description: Wait for another agent to enter WAITING state, then execute follow-up instructions
allowed-tools: Bash(uv run mng list *), Bash(while true; do*)
---

The user's raw arguments are: $1

Parse this as follows: the FIRST WORD is the agent name. Everything after the first word is what to do once the agent is ready. If there is only one word, there are no follow-up instructions.

## Polling Procedure

First, verify the target agent exists and check its current state. Use the agent name (first word only) in this command:

```
uv run mng list --include 'name == "AGENT_NAME"' --format '{name}: {state}'
```

If no output is returned, the agent does not exist. Report the error and stop.

If the agent is already in WAITING, DONE, or STOPPED state, skip the polling loop and proceed directly to the follow-up task.

Otherwise, poll the agent's lifecycle state every 60 seconds until it leaves the RUNNING state. Run the following bash command (with a 600000ms timeout), substituting AGENT_NAME with the first word:

```bash
while true; do
  STATE=$(uv run mng list --include 'name == "AGENT_NAME"' --format '{state}' 2>/dev/null | head -1)
  echo "[$(date '+%H:%M:%S')] Agent 'AGENT_NAME' state: ${STATE:-NOT_FOUND}"
  case "$STATE" in
    WAITING|DONE|STOPPED) echo "Agent 'AGENT_NAME' is ready (state: $STATE)"; break ;;
    "") echo "Agent 'AGENT_NAME' not found, stopping"; break ;;
    *) sleep 60 ;;
  esac
done
```

If this command times out (after 10 minutes), simply re-run the same command. Continue re-running until the agent reaches a terminal state.

## After the Agent is Ready

Once the agent is in WAITING, DONE, or STOPPED state, carry out the follow-up instructions (everything after the first word in the arguments above). If no follow-up instructions were provided, inform the user that the agent is ready.
