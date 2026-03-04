# TUI vs CLI: When to Use Interactive Elements

## Context

`mng` is fundamentally a CLI tool. Most commands are non-interactive: you type a command, it runs, it prints output. But a few commands have interactive elements:

- **Urwid TUI selectors** in `connect` (agent picker) and `cleanup` (multi-select agent picker)
- **Click.confirm prompts** in `destroy`, `snapshot delete`, `issue_reporting`, and agent plugins (`claude_agent`, `skill_agent`)
- **Editor invocation** in `message` (open `$EDITOR` for composing messages)

All interactive elements are gated behind the `is_interactive` flag (auto-detected from TTY, overridable via `--headless`). When not interactive, commands either use sensible defaults (e.g., `connect` picks the most recent agent) or fail with a clear error asking the user to specify the missing argument.

## How git Handles This (and What We Should Learn)

Git is the closest analogue to `mng` in terms of CLI design. Git's approach to interactivity is instructive:

**Git almost never prompts.** It follows two patterns instead:

1. **Explicit opt-in to interactive modes.** `git add -i`, `git add -p`, `git clean -i`, `git rebase -i` -- the user explicitly asks for interactivity with a flag. Without the flag, the command either runs non-interactively or errors.

2. **Require explicit flags instead of confirmation prompts.** `git branch -D` doesn't ask "are you sure?" -- it just does it. The safety comes from requiring `-D` (force) instead of `-d` (safe), not from a y/n prompt. `git push --force` is the same: the danger is gated by a flag, not a prompt.

Git does open an editor for `git commit` (no `-m`) and `git rebase -i`, but these are explicitly part of the workflow, not safety gates.

**What git does NOT do:**
- Fall back to an interactive selector when you omit a required argument. `git checkout` without a branch name doesn't show a branch picker -- it errors.
- Show y/n confirmation prompts for destructive operations. `git branch -D`, `git reset --hard`, `git push --force` all just run.
- Automatically detect TTY and change behavior. (Exception: pager for `git log` output, which is a display concern, not a workflow concern.)

## Recommendation

`mng` should move toward the git model. Specifically:

### 1. TUI selectors should be opt-in, not fallback

Currently, `mng connect` with no agent name falls back to a TUI selector. The git-like approach would be:

- `mng connect` (no agent) -> error: "No agent specified. Use 'mng list' to see agents, or 'mng connect -i' to select interactively."
- `mng connect -i` -> show the urwid selector
- `mng connect my-agent` -> connect directly

This is better because:
- It's predictable. The user always knows what will happen.
- It works the same in scripts and interactive shells.
- It matches the "direct" principle: the command does what you told it to.

The same applies to `cleanup`: `mng cleanup` without filters should require `--yes`/`--force` or `-i`, not silently launch a TUI.

### 2. Confirmation prompts should be replaced by explicit flags where possible

For `destroy`, rather than prompting "are you sure?", consider the git pattern:

- `mng destroy my-agent` -> just destroys it (the user explicitly named what to destroy)
- `mng destroy --all` -> requires `--force` because the blast radius is large

The current confirmation prompt on `destroy` adds friction to a command where the user already explicitly named the target. If they typed `mng destroy my-agent`, they meant it.

For `snapshot delete`, the same logic applies: the user named the snapshot, just delete it.

### 3. Keep confirmation prompts for side-effect-y setup actions

The prompts in `claude_agent` ("install claude?", "trust this directory?") and `skill_agent` ("install this skill?") are appropriate to keep. These are cases where the user ran one command but a *different* action is being proposed as a side effect. The user didn't ask to install anything -- they asked to create an agent, and installation is an unexpected prerequisite. Prompting here is correct.

### 4. Keep editor invocation

`mng message` opening `$EDITOR` when no message is provided follows the `git commit` pattern exactly. This is appropriate.

## Decision Framework

For any new feature, ask these questions in order:

```
Q: Can the user provide this information via a flag or argument?
  YES -> Require them to. Error if they don't.
  NO  -> Q: Is this a side effect the user didn't explicitly request?
           YES -> Prompt (click.confirm). Gate behind is_interactive.
           NO  -> Q: Is there a natural default?
                    YES -> Use the default. Log what you chose.
                    NO  -> Error with a helpful message.

Q: Should we offer an interactive mode for discoverability?
  -> Add a -i/--interactive flag that opts in to a TUI selector.
  -> Never make the TUI the default/fallback path.
```

## Concrete Changes to Consider

| Current Behavior | Proposed Change | Rationale |
|-----------------|----------------|-----------|
| `connect` (no agent) -> TUI selector | Error, suggest `-i` or `mng list` | Git-like: don't change behavior based on TTY |
| `cleanup` (interactive) -> TUI multi-select | Require `-i` for TUI, `--force` for non-interactive | Same |
| `destroy` -> y/n confirm | Just destroy (user named the target) | Git-like: trust explicit commands |
| `snapshot delete` -> y/n confirm | Just delete (user named the target) | Same |
| `claude_agent` install prompt | Keep as-is | Side-effect prompt is appropriate |
| `message` -> editor | Keep as-is | Matches `git commit` pattern |

## Implementation Guidelines

When adding a new interactive element:

1. **Prefer flags over fallback.** Interactive modes should be triggered by `-i`/`--interactive`, not by the absence of a required argument.

2. **Gate side-effect prompts on `is_interactive`.** If not interactive, either auto-approve (with `--auto-approve`) or fail with a clear error.

3. **Reuse existing patterns.** The urwid selector pattern from `connect.py` is good infrastructure. When `-i` is needed, use it.

4. **Keep TUI minimal.** One screen, one job: pick from a list. No multi-step wizards.

5. **Test the non-interactive path first.** All commands must work without a TTY. The interactive path is a convenience for discoverability, not a requirement.

6. **Never change behavior based on TTY detection alone.** This leads to "works on my machine" bugs and confuses users who don't realize their terminal state affects command behavior. Explicit flags are always better.

## Summary

`mng` should follow git's model: commands do what you tell them, error when information is missing, and offer interactive modes as explicit opt-in (`-i`) rather than automatic fallback. Confirmation prompts should be reserved for unexpected side effects, not for commands where the user already specified what they want.
