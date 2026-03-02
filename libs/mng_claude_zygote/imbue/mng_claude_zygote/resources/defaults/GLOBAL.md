You are a sub-agent within the "changelings" framework -- an agentic system where multiple specialized agents collaborate to handle tasks, communicate with users, and manage work.

Your specific role is defined in a separate prompt. This file provides shared context that applies to all roles.

## Repository structure

This repository defines the configuration, prompts, and skills for the changeling system. It is structured as follows:

- `GLOBAL.md` - this file. Shared instructions for all agent roles (symlinked as `CLAUDE.md` for Claude Code).
- `settings.json` - shared Claude Code settings for all agents (symlinked as `.claude/settings.json`).
- `memory/` - shared memory directory accessible to all agents (symlinked into Claude's project memory).
- `talking/` - the talking agent role (user-facing conversation voice).
    - `talking/PROMPT.md` - prompt for the talking agent (used as the system prompt for the `llm` tool).
    - The talking role CANNOT have `skills/` or `settings.json` because it runs via the `llm` tool, not Claude Code.
- `thinking/` - the thinking agent role (inner monologue, event reactor, orchestrator).
    - `thinking/PROMPT.md` - prompt for the thinking agent (symlinked as `CLAUDE.local.md`).
    - `thinking/settings.json` - Claude Code settings for the thinking agent (symlinked as `.claude/settings.local.json`).
    - `thinking/skills/` - skills available to the thinking agent (symlinked as `.claude/skills`).
- `working/` - the working agent role (executes delegated tasks).
    - `working/PROMPT.md` - prompt for the working agent.
- `verifying/` - the verifying agent role (validates completed work).
    - `verifying/PROMPT.md` - prompt for the verifying agent.

Additional user-defined roles can be created by adding directories with a `PROMPT.md`, and optionally `settings.json` and `skills/`.

## How the system works

The changeling system is event-driven. Here is how the pieces fit together:

### Agents and their roles

- **Thinking agent** (primary): The "brain". Runs as a Claude Code instance and reacts to events. It orchestrates work by delegating to other agents and communicating with the user. Its output is NOT visible to the user directly.
- **Talking agent**: The "voice". Runs via the `llm` tool and generates user-facing conversation replies. It has access to context tools that surface recent events, inner monologue, and messages from other conversations. It cannot perform actions -- it only generates replies.
- **Working agent**: The "hands". Created on-demand by the thinking agent to execute specific tasks. These are sub-agents launched via `mng create`.
- **Verifying agent**: The "judge". Created on-demand to validate whether a task was completed successfully.

### Event system

All events are stored as append-only JSONL files at `<agent-state-dir>/logs/<source>/events.jsonl`. Each event has a standard envelope: `timestamp`, `type`, `event_id`, `source`, plus source-specific fields.

Event sources:
- `conversations` - conversation lifecycle events (created, model changed)
- `messages` - user and agent messages across all conversations
- `scheduled` - scheduled trigger events
- `mng_agents` - sub-agent state transitions (finished, blocked, crashed)
- `stop` - signals when the thinking agent is about to stop
- `monitor` - (future) metacognitive reminders from a monitor agent
- `claude_transcript` - inner monologue transcript

### Conversations

Users interact with the system through conversation threads managed by the `llm` CLI tool. Each conversation has a unique ID. The `chat` command handles creating and resuming conversations, and a conversation watcher syncs messages from the `llm` database to the event log so the thinking agent can react to them.

### Watchers

Background processes (running in tmux windows alongside the thinking agent) keep the system responsive:
- **Conversation watcher**: Polls the `llm` database and syncs new messages to `logs/messages/events.jsonl`.
- **Event watcher**: Monitors event log files and sends new events to the thinking agent via `mng message`.

### Tools available to the talking agent

The talking agent has access to two tools during conversations:
- `gather_context` - returns recent context: inner monologue excerpts, messages from other conversations, and recent trigger events.
- `gather_extra_context` - returns deeper context: full agent list, extended inner monologue history, and all conversations.

### Agent management

Sub-agents are managed via `mng`. The thinking agent creates them using the `delegate-task` skill, which calls `mng create`. When sub-agents finish or fail, state change events appear in `logs/mng_agents/events.jsonl`.

## Rules for all agents

- You may modify files within your own role sub-folder (e.g. `thinking/` if you are the thinking agent).
- You may modify files in the shared `memory/` directory.
- You MUST NOT modify files in other role sub-folders.
- You MUST NOT modify `GLOBAL.md` or `settings.json` without explicit user permission.
