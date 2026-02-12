# Overview

Each changeling is deployed as a Modal App with a cron-scheduled function. When triggered, the function uses `mngr create` to spin up a specific `mngr` "agent type" that does its work (creating commits, PRs, reports, etc.) and then shuts down.

# Design principles

1. **Simplicity**: The system should be as simple as possible, both in terms of user experience and internal architecture. Each changeling corresponds to one Modal App and one scheduled function, with minimal moving parts. Each invocation results in one new `mngr` agent that runs to completion and then exits, making it easy to connect and debug.
2. **Modularity**: Each changeling is independent and self-contained. This allows users to mix and match different templates, settings, and schedules without them interfering with each other. It also makes it easier to reason about and debug individual changelings.
3. **Native**: The agents operate directly in GitHub and the user's codebase, creating real commits, PRs, and issues. This ensures that the work they do is visible, actionable, and integrated into the user's existing workflows.
4. **Personal**: Changelings are designed to serve an *individual* user. There are no team features or shared data. Each user's changelings are private, and are intended to act as extensions of themselves. A user should be able to use `changelings` without their boss even knowing, and just look super-productive!

# Deployment model

## What gets deployed

Each changeling is a Modal App containing:

- The full repository contents in question (via a selected cloning strategy, see [Building Images](#building-images) below for options)
- For now, the full imbue monorepo codebase (so `mngr` and all its dependencies are available). Eventually this will be packaged more sensibly.
- A single function decorated with `@modal.Cron(schedule)` that:
  1. Contains the base data for the repo
  2. Calls `mngr create` with the appropriate arguments
  3. Exits immediately (so that you're only charged for the agent runtime)

By default, each changeling is a **separate Modal App** because this makes it easier to deploy them all independently. In the future we may relax this constraint to enable deploying groups of changelings together, but for now one changeling = one Modal App.

## The execution flow

```
Modal Cron trigger
  --> Modal function starts in a fresh container
  --> Puts the secrets into the .env file
  --> Creates a sandbox for this "run" of this changeling by calling:
        mngr create <agent-name> <agent-type> --in modal --no-connect --tag CREATOR=changeling --base-branch main --new-branch changelings/<name>-<date> --env-file .env
  --> Modal function exits, sandbox torn down

Modal agent sandbox:
  --> Sandbox starts, runs the agent code
  --> Agent (Claude) runs, makes commits, creates PR
  --> Agent finishes, mngr returns
  --> Sandbox is torn down / snapshotted
```

By creating a new sandbox for each run, we ensure that each execution of the changeling is isolated and has a clean environment. This also makes it easy to connect to the agent while it's running (and after) for debugging, since it's a standard `mngr` agent running in a Modal sandbox.

## Building images

There are a few different ways that `changelings` can get the codebase into the Modal App for the scheduled function to use when it calls `mngr create`, each with their own trade-offs.

The main options are:

1. **fresh clone from GitHub** (default): the Modal Sandbox (where the agent runs) will use the GITHUB_TOKEN to clone the repo directly from GitHub when the agent starts up. This is simple and ensures that the agent always has the latest code, but it can be slow (especially for large repos) and may run into rate limits or other issues with GitHub. It also does not do anything to install dependencies, so each agent may need to figure that process out for itself, which can be slow and expensive.
2. **snapshot during deploy**: during deployment of the Modal App, we can create a snapshot of an agent container by creating a placeholder agent that simply immediately exits, then saving off that snapshot id. Then, when the agent starts up as a result of the Function invocation, the agent can start from that point and simply pull the latest code from GitHub. This can be much faster, though the agent can end up with an outdated version of the environment over time if there are changes to the dependencies or setup process. It also adds some complexity and latency to the deployment process.
3. **commit-pinned Dockerfile**: this is the strategy used in the `mngr` repo: we create a .tar.gz file of a specific commit hash in the repo (via `make_tar_of_repo.sh`), then include that when we deploy our Modal Function. Then when the Function invokes `mngr create`, it can *also* point at that uploaded .tar.gz of the repo, which is referenced by the Dockerfile for building the image. This is the most complex to set up, but it is very fast, and always stays fully up-to-date. See [this blogpost](TK-link) for more details on this strategy.
4. **custom**: users can also specify their own custom image building strategy if they want by setting the appropriate `mngr` config arguments.

# Configuration

Changeling definitions are stored in `~/.changelings/config.toml`. This is a single file containing all registered changelings for the current user.

This file should **not** be checked into source control!  (since it is user-dependent).  In the future we may also want to mirror this file into a Modal volume (to make it easier for the user to share this config across machines), but for now it only lives locally.

```toml
# which mngr profile to use. Doesn't need to be set, defaults to the default mngr profile.
mngr_profile = "changelings"

# the name of the entry is the unique identifier for this changeling. Runs will use this name.
[changelings.fixme-fairy]
# defaults to the name of the changeling if not specified. This will be passed through to mngr
agent_type = "fixme-fairy"
# defaults to "0 0 * * *" (every night at 3AM in the user's local time) if not specified
schedule = "0 3 * * *"
# defaults to "main" if not specified
branch = "main"
# defaults to true
enabled = true
# if you want to specify extra secrets, use this to forward the value of those env vars to the agent
# (these are forwarded by default, and if you change this setting, you'll probably want to continue including them) 
secrets = ["GITHUB_TOKEN", "ANTHROPIC_API_KEY"]
# other mngr arguments can optionally be specified as well, like:
template = "my-template"
initial_message = "This is a custom message for the agent, overriding the template default"
build_args = ["--no-cache"]
# etc.
```

Because all config variables have defaults, you *should* be able to *just* specify the name, and as long as that is a valid "agent type" in `mngr`, everything should "Just Work".

# Auth and secrets

Any configured secrets are forwarded to the sandbox as environment variables by way of Modal Secrets, and can be used by the agent.

Below are some specific details about generally required secrets for most agents.

## GitHub access

Most changelings need access to GitHub. This is generally done by requiring a `GITHUB_TOKEN` with permissions to do whatever the agent needs to do, eg:
- Clone private repos
- Create branches and push commits
- Create pull requests
- Read and comment on issues (for issue-fixer)

## API keys

The agent (eg, Claude) generally needs an API key. By default, we forward `ANTHROPIC_API_KEY`, though if you need additional keys for other services, you can specify those in the `secrets` config variable and they will be forwarded as well.

## SSH keys

Your local `mngr` SSH public key(s) will be forwarded to the sandbox as well (so that you can access it).

## `mngr` data

By default, all relevant `mngr` data (ex: user id, environment names, etc) will be injected into the deployed App so that the created agents are directly accessible via you.

If you want, you can specify a separate `mngr` profile for use by `changelings` (so that it doesn't clutter up your normal namespace--they will be tagged anyway, but sometimes it's nice not to have to see them).
