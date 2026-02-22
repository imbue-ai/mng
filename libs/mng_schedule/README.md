# mng-schedule

A plugin for [mng](https://github.com/imbue-ai/mng) that adds the `mng schedule` command for scheduling recurring invocations of mng commands on remote providers.

## Overview

`mng schedule` lets you set up cron-scheduled triggers that automatically run mng commands (create, start, message, exec) at regular intervals. This is useful for autonomous agents that should run on a recurring schedule -- for example, a nightly code review agent or a periodic test runner.

## Usage

```bash
# Add a nightly agent that runs at 2am
mng schedule add --command create --args "--type claude --message 'review recent PRs'" --schedule "0 2 * * *" --provider modal

# Add a named trigger
mng schedule add --name nightly-review --command create --schedule "0 3 * * *" --provider modal

# List all active schedules
mng schedule list

# List all schedules including disabled ones
mng schedule list --all

# Update an existing trigger
mng schedule update my-trigger --schedule "0 4 * * *"

# Disable a trigger without removing it
mng schedule update my-trigger --disabled

# Test a trigger by running it immediately
mng schedule run my-trigger

# Run locally instead of on the configured provider
mng schedule run my-trigger --local

# Remove a trigger
mng schedule remove my-trigger

# Remove multiple triggers without confirmation
mng schedule remove trigger-1 trigger-2 --force
```

## Subcommands

- **`add`** -- Create a new scheduled trigger
- **`remove`** -- Remove one or more scheduled triggers
- **`update`** -- Modify fields of an existing trigger
- **`list`** -- List scheduled triggers (default when no subcommand given)
- **`run`** -- Execute a trigger immediately for testing

## Installation

`mng-schedule` is installed as part of the mng monorepo:

```bash
uv sync --all-packages
```

The plugin registers itself automatically via setuptools entry points.
