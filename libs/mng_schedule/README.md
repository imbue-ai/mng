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
- **`list`** -- List scheduled triggers (default when no subcommand given)
- **`run`** -- Execute a trigger immediately for testing

## Packaging code for remote execution

In order to run `mng` commands in a scheduled environment like Modal, there are a few requirements:

1. For the `create` command: the code that the agent will run (e.g. the repo that the agent will clone and work with) needs to either be available in the execution environment (so that it can be injected into the agent) or automatically included via the command (ex: passing `--snapshot <snapshot-id>` to the `create` command).
2. The `mng` CLI needs to be available in the execution environment (so that the command can run at all).
3. The environment variables and files referred to by the command being run also need to be available in the execution environment (so that the executed command runs as expected). 
4. The configuration for `mng` itself needs to be transferred into the execution environment (so that the command executes as expected).

The `mng schedule` plugin takes care of #2 through #4 automatically, and ensures that #1 will happen correctly. 

### 1. Ensuring code availability for `create` commands

There are three primary strategies for ensuring that the project code and data is available to the agent when running a `create` command in a scheduled environment like Modal:

1. Pass in a `--snapshot <snapshot-id>` argument via the `--args` command. If this is provided, no other work needs to be done (though you may want to have your agent update itself when it runs, since the snapshot will grow outdated over time)
2. Pass in a `--git-image-hash <commit-hash>` argument to the `mng schedule add` command, which will automatically package the code at that commit hash into a .tar.gz file, upload it to Modal, and then use the *current* commit hash based Dockerfile (assumed to exist at `.mng/Dockerfile`) for building the Modal images (for both the deployed function and the agents it creates). 
3. Pass in a `--full-copy` flag to the `mng schedule add` command, which will copy the entire codebase into the Modal App's storage during deployment, and then make that available to the agent when it runs. This is the simplest option to set up, but it can be slow for large codebases and may include a lot of unnecessary files.

Failing to provide one of those arguments will result in an error pointing back to this documentation.

### 2. Ensuring `mng` CLI availability for remote execution

The `mng schedule` plugin automatically ensures that the `mng` CLI is available in the execution environment for scheduled commands, even on remote providers like Modal.

This is done by introspecting to understand how `mng_schedule` is installed:

1. if it is installed as a normal remote package, then that package is added as a dependency of the Modal App. This is the normal production method used by most users.
2. if it is installed in editable mode (eg via `pip install -e .`), then the local code is packaged up and uploaded to Modal during deployment, and then used as the source for building the Modal images. This method is primarily used for development.

Note that for #2, the code is packaged via the same "make a snapshot of the repo at a specific commit hash" strategy described above, since this leads to better caching.
In this case, the GH_TOKEN secret is required in order to ensure that the code is fully up-to-date when it is deployed.

### 3. Ensuring environment variable and file availability for remote execution

The `mng schedule` plugin automatically forwards any secrets and files that would be required by the scheduled create or start commands.

If the command is "message" or "exec", no files or environment variables are required.

### 4. Ensuring `mng` configuration availability for remote execution

The `mng schedule` plugin automatically syncs the relevant `mng` configuration for the scheduled command into the execution environment, so that the command runs as expected.
This includes much of the data in `~/.mng/` (except your own personal SSH keys, since those should never be transferred).

In order for you to be able to connect to the newly created agent, `mng schedule add` automatically adds an argument to include your SSH key as a known host for "create" and "start" commands.
