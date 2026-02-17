#!/bin/bash
set -euo pipefail
# This is a (very long) tutorial that covers most of the features of mngr with examples, as well as simple ways to do common tasks.
# See the README.md for details on installation and higher level architecture.

##############################################################################
# CREATING AGENTS
#   One of the most common things you'll want to do with mngr is create agents. There are *tons* of options,
#   so basically any workflow you want should be supported.
##############################################################################

# running mngr is strictly better than running claude! It's one less letter to type :-D
# running this command launches claude (Claude Code) immediately
mngr
# that happens because the defaults are the following: command=create, agent=claude, provider=local, project=current dir

# you can also launch claude remotely in Modal:
mngr --in modal

# when creating agents to accomplish tasks, it's recommended that you give them a name to make it easier to manage them:
mngr my-task
# that command give the agent a name of "my-task". If you don't specify a name, mngr will generate a random one for you.

# you can also specify a different agent (ex: codex)
mngr another-task codex

# you can specify the arguments to the *agent* (ie, send args to claude rather than mngr)
# by using `--` to separate the agent arguments from the mngr arguments:
mngr -- --model opus
# that command launches claude with the "opus" model instead of the default

# you can send an initial message (so you don't have to wait around, eg, while a Modal container starts)
mngr --in modal --no-connect --message "Speed up one of my tests and make a PR on github"
# here we disable the default --connect behavior (because presumably you just wanted to launch that in the background and continue on your way)
# and then we also pass in an explicit message for the agent to start working on immediately
# the message can also be specified as the contents of a file (by using --message-file instead of --message)

# you can also edit the message *while the agent is starting up*, which is very handy for making it "feel" instant:
mngr --in modal --edit-message

# another handy trick is to make the create command "idempotent" so that you don't need to worry about remembering whether you created an agent yet or not:
mngr create sisyphus --reuse
# if that agent already exists, it will be reused (and started) instead of creating a new one. If it doesn't exist, it will be created.

# you can use templates to quickly apply a set of preconfigured options:
mngr my-task -t modal
# templates are defined in your config (see the CONFIGURATION section) and can be stacked: -t modal -t codex

# you can specify which existing host to run on (eg, if you have multiple Modal hosts or SSH servers):
mngr my-task --host my-dev-box
# (--target-host is an alternative form)

# build arguments let you customize the remote host (eg, GPU type, memory, base Docker image for Modal):
mngr my-task --in modal -b gpu=a100 -b memory=16 -b image=python:3.12
# (--build and --build-args are alternative forms of -b; see "mngr create --help" for all provider-specific build args)
# some other useful Modal build args: --region, --timeout, --offline (blocks network), --secret, --cidr-allowlist, --context-dir

# you can mount persistent Modal volumes:
mngr my-task --in modal -b volume=my-data:/data

# you can use an existing snapshot instead of building a new host from scratch:
mngr my-task --in modal --snapshot snap-123abc

# you can pass start arguments to the host provider's start command:
mngr my-task --in modal -s some-start-arg=value
# (--start and --start-args are alternative forms of -s)

# you can run a literal command instead of a named agent type:
mngr my-task --agent-cmd "python my_script.py"

# you can add extra tmux windows that run alongside your agent:
mngr my-task -c server="npm run dev" -c logs="tail -f app.log"
# (--add-cmd and --add-command are alternative forms of -c)

# you can clone from an existing agent's work directory:
mngr my-task --from other-agent
# (--source, --source-agent, and --source-host are alternative forms for more specific control)

# you can run directly in the current directory without creating a worktree:
mngr my-task --in-place
# or explicitly choose to copy or git clone instead of the default worktree:
# --copy creates an isolated copy, --clone creates a git clone sharing objects with the original repo (local agents only)

# you can specify the base branch and create a new branch with a custom name:
mngr my-task --base-branch main --new-branch feature/my-feature
# or disable new branch creation entirely with --no-new-branch (requires --in-place or --copy)
# (--new-branch-prefix controls the prefix for auto-generated branch names, default: mngr/)

# you can make a shallow clone for faster setup:
mngr my-task --depth 1
# (--shallow-since clones since a specific date instead)

# you can set environment variables for the agent:
mngr my-task --env API_KEY=abc123 --env DEBUG=true
# (--env-file loads from a file, --pass-env forwards a variable from your current shell)

# you can also set host-level environment variables (separate from agent env vars):
mngr my-task --in modal --host-env MY_VAR=value
# (--host-env-file and --pass-host-env work the same as their agent counterparts)

# you can grant permissions to the agent:
mngr my-task --grant "Bash(npm test:*)"

# you can upload files and run custom commands during host provisioning:
mngr my-task --in modal --upload-file ~/.ssh/config:/root/.ssh/config --user-command "pip install foo"
# (--sudo-command runs as root; --append-to-file, --prepend-to-file, and --create-directory are also available)

# you can add SSH known hosts for outbound SSH from the agent:
mngr my-task --in modal --known-host "github.com ssh-ed25519 AAAA..."

# you can set an idle timeout so the host shuts down automatically when not in use:
mngr my-task --in modal --idle-timeout 30m
# (--idle-mode controls what counts as idle: io, agent, or disabled)

# you can set the host to auto-restart on boot:
mngr my-task --in modal --start-on-boot

# you can wait for the agent to finish before the command returns (great for scripting):
mngr my-task --no-connect --await-agent-stopped --message "Do the thing"
# (--await-ready waits only until the agent is ready, not until it finishes)

# you can send a message when resuming a stopped agent:
mngr my-task --resume-message "Continue where you left off"
# (--resume-message-file reads the resume message from a file)

# you can control connection retries and timeouts:
mngr my-task --in modal --retry 5 --retry-delay 10s --ready-timeout 30
# (--reconnect / --no-reconnect controls auto-reconnect on disconnect)

# you can use a custom attach command instead of the default terminal attachment:
mngr my-task --attach-command "ssh my-server"

# you can abort creation if the working tree has uncommitted changes:
mngr my-task --ensure-clean

# you can control whether the source work_dir is copied immediately on creation:
mngr my-task --in modal --no-connect --copy-work-dir --message "Work on this snapshot"
# (by default, work_dir is copied if --no-connect and not copied if --connect)

# you can use rsync for file transfer with custom arguments:
mngr my-task --in modal --rsync --rsync-args "--exclude=node_modules"
# (--include-gitignored, --exclude-unclean, and --include-git control what files get transferred)

# you can add labels to organize your agents and tags for host metadata:
mngr my-task --label team=backend --tag env=staging

# you can override the project name (normally derived from git remote or folder name):
mngr my-task --project my-project

# you can name the host separately from the agent:
mngr my-task --in modal --host-name my-modal-box
# (--host-name-style and --name-style control auto-generated name styles for hosts and agents respectively)

# you can override which user the agent runs as:
mngr my-task --user developer

# you can auto-approve all prompts (useful for scripting and CI):
mngr my-task -y --no-connect --message "Do the thing"

# you can control output format for scripting:
mngr my-task --no-connect --format json
# (--json and --jsonl are shorthands; --quiet suppresses all output)

# you can enable or disable specific plugins:
mngr my-task --plugin my-plugin --disable-plugin other-plugin

# you can specify the project context directory (for build context and loading project-specific config):
mngr my-task --context /path/to/project

# you can specify the target path where the agent's work directory will be mounted:
mngr my-task --in modal --target-path /workspace

# you can be super explicit about all of the arguments if you want to be extra safe and make your code easier to understand:
mngr create --name my-task --agent-type claude --in modal

# tons more arguments for anything you could want! As always, you can learn more via --help
mngr create --help

# or see the other commands--list, destroy, message, connect, push, pull, copy, and more!  These other commands are covered in their own sections below.
mngr --help

## CREATING AGENTS PROGRAMMATICALLY

# mngr is very much meant to be used for scripting and automation, so nothing requires interactivity.
# if you want to be sure that interactivity is disabled, you can use the --headless flag:
mngr --headless

# or you can set that option in your config so that it always applies:
mngr config set headless True

# or you can set it as an environment variable:
export MNGR_HEADLESS=True

# *all* mngr options work like that. For example, if you want to always run agents in Modal by default, you can set that in your config:
mngr config set commands.create in modal

# for more on configuration, see the CONFIGURATION section below

##############################################################################
# LISTING AGENTS
#   After you've created a bunch of agents, you might lose track of them! So "mngr list" makes it easy to see all of your agents,
#   as well as any important information about them (ex: where they're running, when they were last active, etc.)
##############################################################################

# TODO: create all of the rest of the *section* headers, like we did for create and list




