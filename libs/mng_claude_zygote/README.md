# Design for "Changelings"

This plugin implements the core functionality for claude-based "changelings": LLM-based agents that can have multiple conversation threads, react to events, and store persistent memories.

The core idea is to have a "primary" agent that serves as the "inner monologue" of the changeling, and that reacts to events (like new messages in conversation threads, scheduled events, sub-agent state changes, etc.)
Rather than having a direct conversation with the agent, the agent has a prompt that tells it what to do in response to various events, and it simply processes those until it decides that everything is complete and it can go to sleep (until it is awoken to process the next event)

In practice, "changelings" are just special mng agents that inherit from the ClaudeZygoteAgent

They can be thought of as a sort of "higher level" agent that is made by assembling a few different LLM-based programs

Fundamentally, changelings are mng agents where:
- The primary agent (from mng's perspective) is a claude code instance *that reacts to "events"* and forms the sort of "inner dialog" of the agent
- Users do *not* chat directly with this main "inner monolouge" agent--instead, they have conversational threads via the "llm live-chat" command-line tool, and those conversations are *exposed* to the primary agent by sending it events to react to.
- The core "inner monologue" agent can be thought of as reacting to events. It is sent messages (by a watcher, via "mng message") whenever:
    - one of the conversation files (<agent-data-dir>/logs/conversations/<conversation-id>.jsonl) gets appended to
    - the rest of the events all happen based on json getting appended to <agent-data-dir>/logs/entrypoint_events.jsonl:
        - one of the time based triggers happens ("mng schedule" can be used, via a skill, to schedule custom events at certain times, which in turn append the json data for that event to <agent-data-dir>/logs/entrypoint_events.jsonl)
        - a sub agent (launched by this primary agent) transitions to "waiting" (happens via our own hooks--goes through a modal hook like snapshot_and_save if remote, otherwise can just call "mng messge" directly)
        - the primary agent tries to stop (for the first time--before thought complete, roughly). This allows it to do a last check of whether there is anything else worth responding to before going to sleep (and considering when it ought to wake)
        - (future) a local monitor agent appends a message/reminder to its file (or calls mng message directly)
- The primary agent is generally instructed to do everything via "mng" (because then all sub agents and work is visible / totally transparent to you)

There are many important implementation details:
- Our general data model is to use append-only jsonl files for all of our data (conversations, events, inner monologue thoughts, etc.) This makes it super easy to keep track of everything that has happened and debug.
- The "conversation threads" or "chat threads" are simply conversation ids that are tracked by the "llm" tool (a 3rd party CLI tool that is really nice and simple--we've made a plugin for it, llm-live-chat, that enables the below "llm live-chat" and "llm inject" commands)
- Users create new (and resume existing) conversations by calling a little "chat" command. It's just a little bash script that creates event json entries and also makes calls to "llm" so that users and agents don't need to remember the exact invocations. "chat --new" for a new chat and "chat --resume <conversation_id>" to resume. "chat" with no arguments lists all current conversation ids
- Agents create new conversations by using their "new chat" skill, which calls "chat --new --as-agent" and passing in the message as well
- Whenever the user (or the agent) creates a new conversation, the "chat" wrapper appends a conversation object to <agent-data-dir>/logs/conversations.jsonl (as a json dict on a single line, with keys for "id" and "model", which comes from the default in <agent-data-dir>/default_chat_model). The conversation object is created by calling "llm live-chat" with the initial message as an arg and correct flags (if it is a user message) or "llm inject" with the right args (if it is an agent message)
- The ClaudeZygoteAgent runs a script in a tmux window that watches the database used by the "llm" tool and, whenever it changes, it looks through all conversations ids from "conversations.jsonl" and all messages for those conversation ids. It then finds any messages that have not yet been appended to their <agent-data-dir>/logs/conversations/<conversation-id>.jsonl file, and does so (in timestamp order, appends the whole json dict for the message as a single line).
- Thus the URL to view an existing chat conversations is simply done via a special ttyd server that accepts an arg of the conversations-id, and uses that to run the correct llm invocation: "llm live-chat --show-history -c --cid <conversations_id>  -m <chat-model>" where chat-model is something like "claude-opus-4.6", and comes from the most recent entry in conversations.jsonl with this id
- To list all conversations for this agent, we can simply look at the <agent-data-dir>/logs/conversations.jsonl file (it contains all conversations. There can be multiple entries for a single conversation id if a different model was selected, ie, it is append-only and the last value wins)
- When invoking the "llm live-chat", we should pass in two tools: one tool for gathering context (which the system promote encourages them to run every time before responding to a new user message) and another tool for gathering extra context (if necessary for their reply)
- The first tool gathers context for the "llm live-chat" calls by collecting any recent chat messages from across the *other* conversations, if any, as well as the most recent "inner monologue" messages (accessible via <agent-data-dir>/logs/transcript.jsonl), and any recent non-message events)
- The second tool that gathers extra context for the "llm live-chat" calls should be able to expose current status of all mng agents (eg, by calling mng list), as well as deeper history for the inner monologue agent.
- A simple watcher should observe <agent-data-dir>/logs/conversations/*.jsonl and <agent-data-dir>/logs/entrypoint_events.jsonl for changes, and when modified, send the next unhandled message(s) to the primary agent (via "mng message")
- Changeling agents are assumed to run from a specially structured git repo that contains various skills, configuration, CLAUDE.md files with prompts, and the code for any tools they have constructed for themselves.
- The top level CLAUDE.md in the agent git repo (where it will be launched) serves as the core system prompt that is *shared* among all agents (the primary agent, any claude subagent it makes, and even any other agents created via mng with this repo as the target)
- The primary agent CLAUDE.md should be checked in as ".changelings/entrypoint.md" and should be symlinked from the project root as "CLAUDE.local.md" when it is the agent that is running (same thing for ".changelings/entrypoint.json", which will be symlinked as ".claude/settings.local.json"). This is something that the ClaudeZygoteAgent should take care of.
- Other agents can be defined by simply making *.md (and *.json) entries in the ".changelings/" folder (and creating an appropriate agent type for them in ".mng/settings.toml", and maybe someday we even auto-gen those entries if missing)
- The prompts for the primary agent (both before shutdown and upon message receipt) should encourage it to keep track of messages that it received (via its own task list)
- *All* claude agents should share the same memory, which should be symlinked between ".changelings/memory/" (in the worktree) and the claude location for memory for a project (~/.claude/projects/<project>/memory/, which then causes the memories to show up as changes to git). This is done during provisioning: since we know the work_dir, we can compute the Claude project directory name (absolute path with / and . replaced by -) and proactively create the directory and symlink without needing to poll
- Any claude agents should use the "project" memory scope (again, to keep memories version controlled)
- As part of getting itself set up, the ClaudeZygoteAgent will need to ensure that we've installed the "llm" tool, as well as our plugins for it (ie, "llm-anthropic" and "llm-live-chat"). In other words, we need to call these commands:
        uv tool install llm
        llm install llm-anthropic
        llm install llm-live-chat

All of the above is basically stuff that should either be done directly by the ClaudeZygoteAgent, or that it should configure such that everything works out (eg, shipping over bash scripts for the "chat" command, etc.)
