# mng_claude_changeling

This plugin implements the core functionality for Claude-based "changelings": composite agents built from multiple mng agents that, together, form a single higher-level agent from the user's perspective.

## What is a changeling?

A changeling is a *collection of persistent mng agents* that serve a web interface and support chat input/output. Each agent within the changeling fulfills a specific **role** (e.g., thinking, working, verifying), and they coordinate through shared event streams in a common git repo.

From mng's perspective, each role is a separate mng agent with its own agent type. Multiple instances of a single role can run simultaneously (e.g., multiple workers). The plugin is responsible for transforming a simple directory of text files (prompts, skills, configuration) into a valid set of mng agent configurations.

## Architecture

### Roles as agent types

Each role directory in the changeling repo corresponds to an mng agent type:

- `thinking/` - the primary "inner monologue" agent that reacts to events and coordinates the changeling
- `talking/` - generates replies to user messages (runs via `llm live-chat`, not Claude Code)
- `working/` - executes actual work tasks, can have skills and tools
- `verifying/` - checks work quality, triggered by "finished" events from sub-agents
- `(user-defined)/` - any additional roles (e.g., "planning/", "researching/")

Each role (except `talking/`) has its own directory structure:

- `<role>/PROMPT.md` - role-specific prompt (symlinked as `CLAUDE.local.md` when active)
- `<role>/.claude/settings.json` - Claude Code settings for the role
- `<role>/.claude/skills/` - skills available to the role
- `<role>/.claude/settings.local.json` - mng-managed hooks (gitignored, written during provisioning)
- `<role>/memory/` - per-role memory (synced into Claude project memory via hooks)

`GLOBAL.md` at the repo root provides shared instructions for all roles, symlinked as `CLAUDE.md` so Claude Code discovers it.

### The primary agent (thinking role)

The "thinking" role is the default primary agent. It does not chat directly with users. Instead, it reacts to events delivered from shared event streams:

- `events/messages/events.jsonl` - new conversation messages (synced from the `llm` database)
- `events/scheduled/events.jsonl` - time-based triggers
- `events/mng_agents/events.jsonl` - sub-agent state transitions (waiting, crashed, done, etc.)
- `events/stop/events.jsonl` - shutdown detection (last chance to check for pending work)
- `events/monitor/events.jsonl` - (future) metacognitive reminders from a monitor agent

### Conversation system

Conversations are stored in the `llm` tool's SQLite database, which serves as the authoritative source of all chat data. The system provides multiple interfaces for interacting with that database:

- **Users** chat via `llm live-chat` through a ttyd web terminal or the `chat` bash script
- **Agents** post messages via `llm inject` (through skills like "send-message-to-user")
- **The conversation watcher** syncs new messages from the database to `events/messages/events.jsonl`
- **The event watcher** delivers those events to the primary agent via `mng message`

This means: user sends message -> `llm` database -> conversation watcher syncs to events -> event watcher delivers to primary agent -> primary agent uses skill to call `llm inject` -> response appears in `llm` database -> user sees it in `llm live-chat`.

### Supporting infrastructure (tmux windows)

The primary agent is augmented with several processes running in additional tmux windows:

- **Conversation watcher** - polls the `llm` SQLite database and syncs new messages to `events/messages/events.jsonl`
- **Event watcher** - monitors event streams and delivers new events to the primary agent via `mng message`
- **Transcript watcher** - converts raw Claude transcript to a common agent-agnostic format
- **Web server** - serves the main web interface with conversation selector and agent list
- **Chat ttyd** - provides web-terminal access to conversations via `llm live-chat`
- **Agent ttyd** - provides web-terminal access to the primary agent's tmux session

## Settings

Per-deployment settings are read from `changelings.toml` in the agent work directory (`$MNG_AGENT_WORK_DIR/changelings.toml`). This file is optional -- all settings have built-in defaults. See `ClaudeChangelingSettings` in `data_types.py` for the full schema.

## Event log structure

All event data uses a consistent append-only JSONL format stored under `<agent-data-dir>/events/<source>/events.jsonl`. Every event line has a standard envelope:

    {"timestamp": "...", "type": "...", "event_id": "...", "source": "<source>", ...additional fields}

Event sources:
- `events/conversations/events.jsonl` - conversation lifecycle events (created, model changed)
- `events/messages/events.jsonl` - all conversation messages across all conversations
- `events/scheduled/events.jsonl` - scheduled triggers
- `events/mng_agents/events.jsonl` - agent state transitions
- `events/stop/events.jsonl` - shutdown detection
- `events/monitor/events.jsonl` - (future) metacognitive reminders
- `events/delivery_failures/events.jsonl` - event delivery failure notifications
- `events/common_transcript/events.jsonl` - agent-agnostic transcript format
- `logs/claude_transcript/events.jsonl` - raw Claude transcript

Every event is self-describing: you never need to know the filename to understand the event. The file organization is a performance/convenience choice, not a correctness one.

## Provisioning

The `ClaudeChangelingAgent.provision()` method transforms the changeling repo into a running agent:

1. Loads settings from `changelings.toml`
2. Validates role constraints (e.g., `talking/` cannot have `.claude/` or skills)
3. Installs the `llm` toolchain (`llm`, `llm-anthropic`, `llm-live-chat`)
4. Provisions default content (GLOBAL.md, role prompts, role configs) for any missing files
5. Creates symlinks for the active role (`.claude` -> `<role>/.claude`, `CLAUDE.md` -> `GLOBAL.md`, `CLAUDE.local.md` -> `<role>/PROMPT.md`)
6. Configures hooks (readiness detection + memory sync) in `<role>/.claude/settings.local.json`
7. Deploys watcher scripts and chat utilities to the host
8. Creates the event log directory structure
9. Sets up per-role memory directories with sync hooks

## Dependencies

This plugin depends on:
- `mng` - the core agent management framework
- `mng-ttyd` - ttyd integration for web terminal access
- `watchdog` - filesystem event monitoring for watchers
