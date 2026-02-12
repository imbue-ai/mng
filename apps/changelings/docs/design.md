# Changelings: Design Document

## Overview

Changelings are scheduled autonomous agents that perform maintenance tasks on a codebase overnight. Each changeling is deployed as a Modal App with a cron-scheduled function. When triggered, the function uses `mngr create` to spin up an agent that does its work (creating commits, PRs, reports, etc.) and then shuts down.

The key insight is that many codebase maintenance tasks are well-suited for autonomous agents: they're repetitive, well-defined, and benefit from running overnight when the developer isn't actively working.

## Goals

- Make it trivial to set up recurring codebase maintenance agents
- Leverage the existing mngr infrastructure (agent types, providers, git integration)
- Provide sensible defaults via built-in templates while allowing full customization
- Keep the system simple: one changeling = one Modal App = one scheduled function

## Deployment model

### What gets deployed

Each changeling becomes a **separate Modal App** containing:

- The full imbue monorepo codebase (so `mngr` and all its dependencies are available)
- A single function decorated with `@modal.Cron(schedule)` that:
  1. Clones the target repository (or checks out the right branch)
  2. Calls `mngr create` with the appropriate arguments
  3. Waits for the agent to finish
  4. Exits (Modal shuts down the sandbox)

### Why separate Modal Apps (not one big one)

- Independent scaling and scheduling
- Failure isolation: one broken changeling doesn't affect others
- Independent deploy/undeploy lifecycle
- Clearer billing and resource attribution
- Simpler reasoning about what's running

### The execution flow

```
Modal Cron trigger
  --> Modal function starts in a fresh sandbox
  --> Clone target repo (git clone)
  --> Set up auth (GITHUB_TOKEN, SSH keys, etc.)
  --> mngr create --in local --no-connect --await-agent-stopped \
        --message "<prompt>" --agent-type claude \
        --base-branch main --new-branch changelings/<name>-<date> \
        --grant github \
        [extra args from template/config]
  --> Agent (Claude) runs, makes commits, creates PR
  --> Agent finishes, mngr returns
  --> Modal function exits, sandbox torn down
```

### Why `--in local` (not `--in modal`)

The Modal function itself IS the sandbox environment. Running `mngr create --in modal` inside it would create a nested Modal sandbox, which is unnecessary complexity. Instead, we run the agent locally within the Modal function's sandbox using `--in local`.

## Configuration

### Where configs live

Changeling definitions are stored in `~/.changelings/config.toml`. This is a single file containing all registered changelings for the current user.

```toml
[changelings.nightly-fixmes]
template = "fixme-fairy"
schedule = "0 3 * * *"
repo = "git@github.com:myorg/myrepo.git"
branch = "main"
agent_type = "claude"
enabled = true

[changelings.weekly-tests]
template = "test-troll"
schedule = "0 4 * * 1"
repo = "git@github.com:myorg/myrepo.git"
branch = "main"
agent_type = "claude"
enabled = true
```

### Template system

Each template provides:

- A default initial message (prompt) for the agent
- Default mngr create arguments (permissions, env vars, etc.)
- A description of what the changeling does

Users can override the default message and add extra mngr args per-changeling.

## Built-in templates

### Fixme Fairy (`fixme-fairy`)

- **Purpose**: Find all FIXMEs/TODOs in the codebase and fix them
- **Behavior**: Creates one commit per fix, then opens a single PR with all fixes
- **Branch naming**: `changelings/fixme-fairy-<date>`
- **PR title**: "Fixme Fairy: Fixed N FIXMEs"

### Test Troll (`test-troll`)

- **Purpose**: Improve the test suite
- **Behavior**: Looks for opportunities to speed up tests, remove pointless tests, fix flaky tests, and increase coverage. Creates one commit per improvement
- **Branch naming**: `changelings/test-troll-<date>`
- **PR title**: "Test Troll: N test improvements"

### Coverage Hunter (`coverage-hunter`)

- **Purpose**: Specifically focused on increasing test coverage
- **Behavior**: Analyzes coverage reports, identifies the most impactful files to add tests for, writes tests that increase coverage without sacrificing speed
- **Branch naming**: `changelings/coverage-hunter-<date>`
- **PR title**: "Coverage Hunter: Added tests for N files (X% -> Y% coverage)"

### Reporting templates

These produce markdown reports rather than code changes:

- **Doc Reporter** (`doc-reporter`): Finds places where documentation and code disagree
- **Docstring Reporter** (`docstring-reporter`): Finds outdated or inaccurate docstrings
- **Security Reporter** (`security-reporter`): Identifies potential security issues

Reports are committed to a `reports/` directory on a branch and a PR is opened, or posted as GitHub issues (configurable).

### Issue Fixer (`issue-fixer`)

- **Purpose**: Watch for new GitHub issues and attempt to fix them
- **Behavior**: Reads recent issues, picks one that seems fixable, creates a PR
- **Branch naming**: `changelings/issue-<number>-<slug>`
- **PR title**: "Issue Fixer: Fix #N - <issue title>"
- **Note**: Should only attempt issues that look tractable (small bug fixes, documentation issues, simple feature requests)

### Code Custodian (`code-custodian`)

- **Purpose**: Act as a "code owner" for a specific sub-module
- **Behavior**: Reviews the sub-module for quality issues, code smells, missing tests, outdated patterns, etc. Creates targeted improvements
- **Extra config**: Requires a `scope` parameter specifying which directory/module to focus on
- **Branch naming**: `changelings/custodian-<scope>-<date>`

## Auth and secrets

### GitHub access

Changelings need a `GITHUB_TOKEN` with permissions to:
- Clone private repos
- Create branches and push commits
- Create pull requests
- Read and comment on issues (for issue-fixer)

This token is passed as a Modal secret and forwarded to the agent via `--grant github` and `--env GITHUB_TOKEN=...`.

### API keys

The agent (Claude) needs an API key. This is passed as a Modal secret and forwarded to the agent's environment.

### SSH keys

For cloning private repos via SSH, the changeling's Modal sandbox needs access to SSH keys. These are configured as Modal secrets.

## CLI commands

### `changeling add <name>`

Register a new changeling in the local config.

Required flags: `--template`, `--repo`, `--schedule`

Optional flags: `--branch`, `--message`, `--agent-type`, `--enabled/--disabled`

### `changeling remove <name>`

Remove a changeling from the local config. With `--force`, also undeploy from Modal.

### `changeling list`

Display all registered changelings with their template, schedule, repo, and enabled status.

### `changeling deploy [name | --all]`

Deploy changeling(s) to Modal. Creates/updates the Modal App for each specified changeling.

### `changeling run <name>`

Run a changeling immediately, bypassing the cron schedule. Useful for testing.

With `--local`, runs entirely locally (no Modal) for rapid iteration.

### `changeling status [name | --all]`

Check the deployment status and recent run history of changeling(s). Shows whether deployed, last run time, last run outcome, and links to any PRs created.

## Open questions

- **Image caching**: Should we build and cache a base Modal image with our codebase, or rebuild each time? Caching is faster but needs a rebuild mechanism when the codebase changes
- **Concurrency**: What happens if a changeling is still running when the next cron trigger fires? Should we skip, queue, or run in parallel?
- **Rate limiting**: Should there be a limit on how many PRs a changeling can create per day/week?
- **Result tracking**: Where do we store run history and outcomes? Modal logs? A separate database? GitHub issues?
- **Multi-repo**: Should a single changeling be able to target multiple repos?
- **Notifications**: Should changelings notify (Slack, email) when they complete or fail?
