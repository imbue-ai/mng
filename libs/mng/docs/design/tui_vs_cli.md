# TUI vs CLI: When to Use Interactive Elements

## Context

`mng` is fundamentally a CLI tool. Most commands are non-interactive: you type a command, it runs, it prints output. But a few commands have interactive elements:

- **Urwid TUI selectors** in `connect` (agent picker) and `cleanup` (multi-select agent picker)
- **Click.confirm prompts** in `destroy`, `snapshot delete`, `issue_reporting`, and agent plugins (`claude_agent`, `skill_agent`)
- **Editor invocation** in `message` (open `$EDITOR` for composing messages)

All interactive elements are gated behind the `is_interactive` flag (auto-detected from TTY, overridable via `--headless`). When not interactive, commands either use sensible defaults (e.g., `connect` picks the most recent agent) or fail with a clear error asking the user to specify the missing argument.

## Recommendation: Keep the Current Approach

The current approach is sound and consistent with the core principles. Here is why, and a framework for deciding future cases.

## Decision Framework

Interactive elements should be used **only** when all of these conditions are met:

### 1. The user omitted required information that cannot be defaulted

The primary trigger for interactivity is **disambiguation**: the user asked to do something but didn't say *what* to do it to, and there's no obvious default.

- `mng connect` without an agent name -- which of the 15 running agents? (TUI selector)
- `mng cleanup` without `--force` -- which agents should be destroyed? (TUI multi-selector)

If there's an obvious default (e.g., `connect` defaults to the most recent agent in headless mode), prefer that over prompting.

### 2. The action is destructive or irreversible

Confirmation prompts are appropriate for **destructive operations** where a mistake costs real work:

- `mng destroy` -- permanently removes agents and their data
- `mng snapshot delete` -- permanently removes a snapshot

These are standard CLI safety patterns (like `rm -i` or `git clean -i`). They should always be skippable with `--force` / `--yes`.

### 3. The action is a one-time setup that the user may not expect

Prompts during provisioning (e.g., "install claude?", "trust this directory?") are appropriate because:

- They happen once, not on every invocation
- They modify the user's system in ways they may not have anticipated
- Saying "no" is a reasonable and common choice

### When NOT to add interactive elements

- **Do not add TUI for things the user can specify via flags.** If the user *can* provide the information on the command line, they should. The TUI is a fallback for when they didn't, not a primary interface.

- **Do not add TUI for configuration or settings.** `mng config set` is the right interface for changing settings. A TUI config editor would violate the "direct" principle -- the user should know exactly what they're changing and how.

- **Do not add TUI for output/display.** Commands like `list`, `events`, `exec` should print their output and exit. A live-updating dashboard or watch mode is a different product concern (and should be a separate command like `mng watch` if ever built, not bolted onto existing commands).

- **Do not add interactive prompts in the middle of a long-running operation.** If provisioning might need user input, collect it upfront or fail early. Blocking on a prompt 30 seconds into a build is a poor experience.

- **Do not add interactivity for choices that can be resolved by convention.** If `mng push` could target multiple agents, pick the one with the matching project label rather than prompting.

## Where the Current TUI is Justified

| Command | Interactive Element | Justification |
|---------|-------------------|---------------|
| `connect` (no agent) | Urwid agent selector | Disambiguation: many agents to choose from, with search/filter |
| `cleanup` (no `--force`) | Urwid multi-select | Destructive + disambiguation: selecting which agents to destroy |
| `destroy` (no `--force`) | Click confirm | Destructive: permanent data loss |
| `snapshot delete` | Click confirm | Destructive: permanent data loss |
| `message` (no message) | Editor | Standard CLI pattern for composing long text (`git commit`, etc.) |
| `claude_agent` install | Click confirm | One-time setup: modifying user's system |
| `claude_agent` trust | Click confirm | One-time setup: modifying user's config |
| `skill_agent` install | Click confirm | One-time setup: modifying user's system |
| `issue_reporting` | Click confirm | Opt-in: sending data to external service |

## Where to Consider Adding Interactivity in the Future

These are cases where interactivity *might* make sense, following the framework above:

- **`mng destroy` without an agent name**: Currently errors. Could show an agent selector like `connect` does, since the operation is both ambiguous and destructive. However, this is also dangerous -- accidentally selecting the wrong agent in a "destroy" selector is worse than in a "connect" selector. A confirmation prompt after selection would mitigate this.

- **`mng start` / `mng stop` without an agent name**: Could show a selector filtered to stopped/running agents respectively. Lower risk than destroy.

- **`mng pull` / `mng push` without an agent name**: Could show a selector. These are data operations, so the risk is moderate (you might clobber local changes with `pull`).

Cases where interactivity should **not** be added:

- `mng create` -- the command already has sensible defaults for everything. Adding a wizard-style TUI would slow down the most common operation.
- `mng list` -- this is a read-only display command. Its job is to print and exit.
- `mng config` -- use the existing key-value interface.

## Implementation Guidelines

When adding a new interactive element:

1. **Always gate on `is_interactive`**: Check `mng_ctx.is_interactive` before any interactive call. Provide a non-interactive fallback (error with clear message, or sensible default).

2. **Always provide a bypass flag**: `--force`, `--yes`, or an explicit argument that removes the need for the prompt.

3. **Reuse existing patterns**: The `select_agent_interactively` function in `connect.py` and the cleanup selector both follow the same urwid pattern with search, keyboard navigation, and status bar. Reuse these rather than inventing new UI paradigms.

4. **Keep TUI minimal**: The urwid selectors work because they do one thing (pick an agent from a list). Do not build complex multi-screen TUI flows.

5. **Test the non-interactive path**: All commands must work in headless mode. The interactive path is a convenience, not a requirement.

## Summary

The current balance is good. `mng` is a CLI tool with light interactive fallbacks for disambiguation and destructive confirmation. This matches user expectations for a tool in the `git`/`docker`/`kubectl` family. The key principle: **interactivity is a fallback for missing information, not a primary interface.**
