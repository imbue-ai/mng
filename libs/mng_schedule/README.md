# mng-schedule

Run AI agents on a schedule.

A plugin for [mng](https://github.com/imbue-ai/mng) that adds the `mng schedule` command for scheduling recurring invocations of `mng` commands (even on remote providers)

## Overview

`mng schedule` lets you set up cron-scheduled triggers that automatically run `mng` commands (create, start, message, exec) at regular intervals. 
This is useful for autonomous agents that should run on a recurring schedule -- for example, a nightly code review agent or a periodic test runner.

## Usage

```bash
# Add a nightly agent that runs at 2am in modal
mng schedule add --command create --args "--type claude --message 'review recent PRs' --in modal" --schedule "0 2 * * *" --provider modal

# Add a named trigger that runs locally
mng schedule add nightly-test-checker --command create --args "--message 'make sure all tests are passing'" --schedule "0 3 * * *" --provider local

# List all active local schedules
mng schedule list --provider local

# List all modal schedules including disabled ones
mng schedule list --provider modal --all

# Update an existing trigger
mng schedule update my-trigger --schedule "0 4 * * *"

# Disable a trigger without removing it
mng schedule update my-trigger --disabled

# Test a trigger by running it immediately
mng schedule run my-trigger

# Remove a trigger
mng schedule remove my-trigger

# Remove multiple triggers without confirmation
mng schedule remove trigger-1 trigger-2 --force
```

## Subcommands

Run `mng schedule <subcommand> --help` for more details on each subcommand:

- **`add`** -- Create a new scheduled trigger
- **`remove`** -- Remove one or more scheduled triggers
- **`update`** -- Modify fields of an existing trigger
- **`list`** -- List scheduled triggers
- **`run`** -- Execute a trigger immediately for testing

## Packaging code for remote execution

In order to run `mng` commands in a scheduled environment like Modal, there are a few requirements:

1. For the `create` command: the code that the agent will run (e.g. the repo that the agent will clone and work with) needs to either be available in the execution environment (so that it can be injected into the agent) or automatically included via the command (ex: passing `--snapshot <snapshot-id>` to the `create` command).
2. The `mng` CLI needs to be available in the execution environment (so that the command can run at all).
3. The environment variables and files referred to by the command being run also need to be available in the execution environment (so that the executed command runs as expected). 
4. The configuration for `mng` itself needs to be transferred into the execution environment (so that the command executes as expected).

The `mng schedule` plugin takes care of #2 through #4 automatically, and ensures that #1 will happen correctly. 

### 1. Ensuring code availability for `create` commands

The image is built in two stages:

1. **Base image (mng environment):** Built from the mng Dockerfile (bundled in the mng package at `imbue/mng/resources/Dockerfile`), which provides a complete environment with system deps, Python, uv, Claude Code, and mng installed. For editable installs, the mng monorepo is packaged and used as the build context. For package installs, a modified Dockerfile installs mng from PyPI instead.
2. **Target repo layer:** The user's project is packaged as a tarball at a specific git commit and extracted into the container at a configurable path (default `/code/project`, controlled by `--target-dir`). WORKDIR is set to this location.

On first deploy, the current HEAD commit hash is automatically resolved and the plugin verifies that the branch has been pushed to the remote. The resolved hash is cached in `~/.mng/build/<repo-hash>/commit_hash` so that subsequent deploys from the same repo reuse the same commit hash (delete the file to force re-resolution).

There are also two alternative strategies that are not yet implemented:

1. Pass `--snapshot <snapshot-id>` to `mng schedule add` to use an existing snapshot as the code source. **Not yet implemented.**
2. Pass `--full-copy` to `mng schedule add` to copy the entire codebase into Modal storage during deployment. **Not yet implemented.**

#### Auto-merge at runtime

By default (`--auto-merge`), the scheduled function fetches and merges the latest code from the deployed branch before each run, so the agent always works with up-to-date code. This requires `GH_TOKEN` or `GITHUB_TOKEN` to be available in the deployed environment (via `--pass-env` or `--env-file`).

Use `--no-auto-merge` to skip this step, or `--auto-merge-branch <branch>` to merge from a specific branch (defaults to the current branch at deploy time).

### 2. Ensuring `mng` CLI availability for remote execution

The `mng schedule` plugin automatically ensures that the `mng` CLI is available in the execution environment. The base image is built from the mng Dockerfile, which already includes mng and all its dependencies.

The install mode is controlled by `--mng-install-mode` (default: `auto`, which auto-detects):

1. **editable:** The mng monorepo source is packaged and used as the Dockerfile build context. The Dockerfile extracts it, runs `uv sync`, and installs mng as a tool. This is the development workflow.
2. **package:** A modified version of the mng Dockerfile is generated that installs mng from PyPI via `uv pip install --system mng mng-schedule` instead of from source.
3. **skip:** Assumes mng is already available (not currently supported for schedule deployments).

### 3. Ensuring environment variable and file availability for remote execution

The `mng schedule` plugin automatically forwards any secrets and files that would be required by the scheduled create or start commands.

If the command is "message" or "exec", no files or environment variables are required.

### 4. Ensuring `mng` configuration availability for remote execution

The `mng schedule` plugin automatically syncs the relevant `mng` configuration for the scheduled command into the execution environment, so that the command runs as expected.
This includes much of the data in `~/.mng/` (except your own personal SSH keys, since those should never be transferred).

In order for you to be able to connect to the newly created agent, `mng schedule add` automatically adds an argument to include your SSH key as a known host for "create" and "start" commands.
