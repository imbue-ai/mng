#!/bin/bash
set -euo pipefail
# This is a (very long) tutorial that covers most of the features of mng with examples, as well as simple ways to do common tasks.
# See the README.md for details on installation and higher level architecture.

##############################################################################
# CREATING AGENTS
#   One of the most common things you'll want to do with mng is create agents. There are *tons* of options,
#   so basically any workflow you want should be supported.
##############################################################################

# running mng is strictly better than running claude! It's one less letter to type :-D
# running this command launches claude (Claude Code) immediately
mng
# that happens because the defaults are the following: command=create, agent=claude, provider=local, project=current dir

# you can also launch claude remotely in Modal:
mng --in modal

# when creating agents to accomplish tasks, it's recommended that you give them a name to make it easier to manage them:
mng my-task
# that command give the agent a name of "my-task". If you don't specify a name, mng will generate a random one for you.

# you can also specify a different agent (ex: codex)
mng another-task codex

# you can specify the arguments to the *agent* (ie, send args to claude rather than mng)
# by using `--` to separate the agent arguments from the mng arguments:
mng -- --model opus
# that command launches claude with the "opus" model instead of the default

# you can send an initial message (so you don't have to wait around, eg, while a Modal container starts)
mng --in modal --no-connect --message "Speed up one of my tests and make a PR on github"
# here we disable the default --connect behavior (because presumably you just wanted to launch that in the background and continue on your way)
# and then we also pass in an explicit message for the agent to start working on immediately
# the message can also be specified as the contents of a file (by using --message-file instead of --message)

# you can also edit the message *while the agent is starting up*, which is very handy for making it "feel" instant:
mng --in modal --edit-message

# another handy trick is to make the create command "idempotent" so that you don't need to worry about remembering whether you created an agent yet or not:
mng create sisyphus --reuse
# if that agent already exists, it will be reused (and started) instead of creating a new one. If it doesn't exist, it will be created.

# you can use templates to quickly apply a set of preconfigured options:
mng my-task -t modal
# templates are defined in your config (see the CONFIGURATION section) and can be stacked: -t modal -t codex

# you can specify which existing host to run on (eg, if you have multiple Modal hosts or SSH servers):
mng my-task --host my-dev-box
# (--target-host is an alternative form)

# build arguments let you customize the remote host (eg, GPU type, memory, base Docker image for Modal):
mng my-task --in modal -b gpu=a100 -b memory=16 -b image=python:3.12
# (--build and --build-args are alternative forms of -b; see "mng create --help" for all provider-specific build args)
# some other useful Modal build args: --region, --timeout, --offline (blocks network), --secret, --cidr-allowlist, --context-dir

# you can mount persistent Modal volumes:
mng my-task --in modal -b volume=my-data:/data

# you can use an existing snapshot instead of building a new host from scratch:
mng my-task --in modal --snapshot snap-123abc

# you can pass start arguments to the host provider's start command:
mng my-task --in modal -s some-start-arg=value
# (--start and --start-args are alternative forms of -s)

# you can run a literal command instead of a named agent type:
mng my-task --agent-cmd "python my_script.py"

# you can add extra tmux windows that run alongside your agent:
mng my-task -c server="npm run dev" -c logs="tail -f app.log"
# (--add-cmd and --add-command are alternative forms of -c)

# you can clone from an existing agent's work directory:
mng my-task --from other-agent
# (--source, --source-agent, and --source-host are alternative forms for more specific control)

# you can run directly in the current directory without creating a worktree:
mng my-task --in-place
# or explicitly choose to copy or git clone instead of the default worktree:
# --copy creates an isolated copy, --clone creates a git clone sharing objects with the original repo (local agents only)

# you can specify the base branch and create a new branch with a custom name:
mng my-task --base-branch main --new-branch feature/my-feature
# or disable new branch creation entirely with --no-new-branch (requires --in-place or --copy)
# (--new-branch-prefix controls the prefix for auto-generated branch names, default: mng/)

# you can make a shallow clone for faster setup:
mng my-task --depth 1
# (--shallow-since clones since a specific date instead)

# you can set environment variables for the agent:
mng my-task --env API_KEY=abc123 --env DEBUG=true
# (--env-file loads from a file, --pass-env forwards a variable from your current shell)

# you can also set host-level environment variables (separate from agent env vars):
mng my-task --in modal --host-env MY_VAR=value
# (--host-env-file and --pass-host-env work the same as their agent counterparts)

# you can grant permissions to the agent:
mng my-task --grant "Bash(npm test:*)"

# you can upload files and run custom commands during host provisioning:
mng my-task --in modal --upload-file ~/.ssh/config:/root/.ssh/config --user-command "pip install foo"
# (--sudo-command runs as root; --append-to-file, --prepend-to-file, and --create-directory are also available)

# you can add SSH known hosts for outbound SSH from the agent:
mng my-task --in modal --known-host "github.com ssh-ed25519 AAAA..."

# you can set an idle timeout so the host shuts down automatically when not in use:
mng my-task --in modal --idle-timeout 30m
# (--idle-mode controls what counts as idle: io, agent, or disabled)

# you can set the host to auto-restart on boot:
mng my-task --in modal --start-on-boot

# you can wait for the agent to finish before the command returns (great for scripting):
mng my-task --no-connect --await-agent-stopped --message "Do the thing"
# (--await-ready waits only until the agent is ready, not until it finishes)

# you can send a message when resuming a stopped agent:
mng my-task --resume-message "Continue where you left off"
# (--resume-message-file reads the resume message from a file)

# you can control connection retries and timeouts:
mng my-task --in modal --retry 5 --retry-delay 10s --ready-timeout 30
# (--reconnect / --no-reconnect controls auto-reconnect on disconnect)

# you can use a custom attach command instead of the default terminal attachment:
mng my-task --attach-command "ssh my-server"

# you can abort creation if the working tree has uncommitted changes:
mng my-task --ensure-clean

# you can control whether the source work_dir is copied immediately on creation:
mng my-task --in modal --no-connect --copy-work-dir --message "Work on this snapshot"
# (by default, work_dir is copied if --no-connect and not copied if --connect)

# you can use rsync for file transfer with custom arguments:
mng my-task --in modal --rsync --rsync-args "--exclude=node_modules"
# (--include-gitignored, --exclude-unclean, and --include-git control what files get transferred)

# you can add labels to organize your agents and tags for host metadata:
mng my-task --label team=backend --tag env=staging

# you can override the project name (normally derived from git remote or folder name):
mng my-task --project my-project

# you can name the host separately from the agent:
mng my-task --in modal --host-name my-modal-box
# (--host-name-style and --name-style control auto-generated name styles for hosts and agents respectively)

# you can override which user the agent runs as:
mng my-task --user developer

# you can auto-approve all prompts (useful for scripting and CI):
mng my-task -y --no-connect --message "Do the thing"

# you can control output format for scripting:
mng my-task --no-connect --format json
# (--json and --jsonl are shorthands; --quiet suppresses all output)

# you can enable or disable specific plugins:
mng my-task --plugin my-plugin --disable-plugin other-plugin

# you can specify the project context directory (for build context and loading project-specific config):
mng my-task --context /path/to/project

# you can specify the target path where the agent's work directory will be mounted:
mng my-task --in modal --target-path /workspace

# you can be super explicit about all of the arguments if you want to be extra safe and make your code easier to understand:
mng create --name my-task --agent-type claude --in modal

# tons more arguments for anything you could want! As always, you can learn more via --help
mng create --help

# or see the other commands--list, destroy, message, connect, push, pull, copy, and more!  These other commands are covered in their own sections below.
mng --help

## CREATING AGENTS PROGRAMMATICALLY

# mng is very much meant to be used for scripting and automation, so nothing requires interactivity.
# if you want to be sure that interactivity is disabled, you can use the --headless flag:
mng --headless

# or you can set that option in your config so that it always applies:
mng config set headless True

# or you can set it as an environment variable:
export MNG_HEADLESS=True

# *all* mng options work like that. For example, if you want to always run agents in Modal by default, you can set that in your config:
mng config set commands.create in modal

# for more on configuration, see the CONFIGURATION section below

##############################################################################
# LISTING AGENTS
#   After you've created a bunch of agents, you might lose track of them! So "mng list" makes it easy to see all of your agents,
#   as well as any important information about them (ex: where they're running, when they were last active, etc.)
##############################################################################

##############################################################################
# CONNECTING TO AGENTS
#   If you've disconnected from an agent (or created one with --no-connect),
#   you can reconnect to it at any time.
##############################################################################


##############################################################################
# SENDING MESSAGES TO AGENTS
#   You can send messages to running agents without connecting to them.
#   This is useful for giving agents new instructions while they work.
##############################################################################


##############################################################################
# EXECUTING COMMANDS ON AGENTS
#   Run shell commands on an agent's host without connecting interactively.
#   Useful for scripting, checking status, or running one-off operations.
##############################################################################


##############################################################################
# OPENING AGENTS IN THE BROWSER
#   Some agents expose web interfaces. "mng open" launches them in your
#   browser, so you can interact with agents visually.
##############################################################################


##############################################################################
# PUSHING FILES TO AGENTS
#   Push local files or git commits to a running agent. This is how you
#   sync your local changes to an agent's workspace.
##############################################################################


##############################################################################
# PULLING FILES FROM AGENTS
#   Pull files or git commits from an agent back to your local machine.
#   This is how you retrieve an agent's work.
##############################################################################


##############################################################################
# PAIRING WITH AGENTS
#   Continuously sync files between your local machine and an agent in
#   real time. Great for working alongside an agent on the same codebase.
##############################################################################


##############################################################################
# STARTING AND STOPPING AGENTS
#   Stopped agents can be restarted, and running agents can be stopped to
#   free resources. Stopping can optionally create a snapshot for later.
##############################################################################


##############################################################################
# RENAMING AGENTS
#   Rename an agent to something more descriptive, or to avoid name
#   collisions.
##############################################################################


##############################################################################
# DESTROYING AGENTS
#   When you're done with an agent, destroy it to clean up all of its
#   resources (host, snapshots, volumes, etc.).
##############################################################################


##############################################################################
# CLONING AND MIGRATING AGENTS
#   Clone an agent to create a copy of it (on the same or different host),
#   or migrate an agent to move it to a different host entirely.
##############################################################################


##############################################################################
# MANAGING SNAPSHOTS
#   Snapshots capture the filesystem state of a host. You can create, list,
#   and destroy them, and use them to restore or fork agents.
##############################################################################


##############################################################################
# PROVISIONING AGENTS
#   Re-run provisioning steps on an existing agent, such as installing
#   packages, uploading files, or running setup commands.
##############################################################################


##############################################################################
# MANAGING AGENT LIMITS
#   Configure idle timeouts, activity tracking, permissions, and other
#   runtime limits for agents and hosts.
##############################################################################


##############################################################################
# CLEANING UP RESOURCES
#   Bulk-destroy or stop agents based on filters like age, idle time, or
#   provider. Also garbage-collect unused resources like orphaned snapshots
#   and volumes.
##############################################################################


##############################################################################
# VIEWING LOGS
#   View log files for agents and hosts. Useful for debugging and
#   monitoring what your agents are up to.
##############################################################################


##############################################################################
# MANAGING PLUGINS
#   List, enable, and disable plugins that extend mng with new agent types,
#   provider backends, and CLI commands.
##############################################################################


##############################################################################
# CONFIGURATION
#   Customize mng's behavior via configuration files. Set defaults for
#   commands, define create templates, and configure providers.
##############################################################################


##############################################################################
# COMMON TASKS
#   Quick recipes for the things you'll do most often: launching an agent
#   on a task, checking on it, grabbing its work, and cleaning up after.
##############################################################################


##############################################################################
# PROJECTS
#   Agents are automatically associated with a project (the git repo you
#   run mng from). Use projects to organize agents and filter your list.
##############################################################################


##############################################################################
# MULTI-AGENT WORKFLOWS
#   Run multiple agents in parallel on different tasks, coordinate their
#   work, and bring everything together.
##############################################################################


##############################################################################
# WORKING WITH GIT
#   Push and pull git commits (not just files) between your machine and
#   agents. Branch management, merge strategies, and worktree support.
##############################################################################


##############################################################################
# LABELS AND FILTERING
#   Tag agents with labels and use CEL filter expressions to target
#   specific agents across list, destroy, cleanup, and other commands.
##############################################################################


##############################################################################
# CREATE TEMPLATES
#   Define reusable presets that bundle common options (provider, build
#   args, permissions, environment, etc.) into a single template name.
##############################################################################


##############################################################################
# CUSTOM AGENT TYPES
#   Define your own agent types in config, or use any command in your PATH
#   as an agent. Wrap existing tools with custom defaults and permissions.
##############################################################################


##############################################################################
# ENVIRONMENT VARIABLES
#   Pass environment variables to agents during creation, control mng
#   behavior via env vars, and understand the variables mng sets for you.
##############################################################################


##############################################################################
# RUNNING AGENTS ON MODAL
#   Launch agents in Modal sandboxes for full isolation, GPU access, and
#   cloud-based execution. Custom images, secrets, volumes, and networking.
##############################################################################


##############################################################################
# RUNNING AGENTS IN DOCKER
#   Run agents in Docker containers for local isolation without cloud
#   costs. Good for untrusted code or reproducible environments.
##############################################################################


##############################################################################
# RUNNING AGENTS LOCALLY
#   The simplest and fastest option. Agents run directly on your machine
#   with no isolation overhead. Best for trusted agents and quick tasks.
##############################################################################


##############################################################################
# IDLE DETECTION AND TIMEOUTS
#   Automatically pause or stop agents when they go idle to save resources.
#   Configure what counts as "activity" and how long to wait.
##############################################################################


##############################################################################
# PERMISSIONS
#   Grant agents specific capabilities (like network access or filesystem
#   writes) and revoke them. Permissions are enforced by plugins.
##############################################################################


##############################################################################
# MULTIPLE AGENTS ON ONE HOST
#   Run several agents on the same host to share resources and reduce
#   costs. Agents share the host filesystem and network.
##############################################################################


##############################################################################
# SCRIPTING AND AUTOMATION
#   Use mng in shell scripts, CI pipelines, and cron jobs. JSON output,
#   headless mode, idempotent creation, and programmatic control.
##############################################################################


##############################################################################
# OUTPUT FORMATS AND MACHINE-READABLE OUTPUT
#   Switch between human-readable, JSON, and JSONL output. Use --format
#   with templates, pipe output to jq, and build tooling on top of mng.
##############################################################################


##############################################################################
# DEVCONTAINER HOOKS
#   Use devcontainer lifecycle hooks (onCreateCommand, postStartCommand,
#   etc.) to customize agent environments during provisioning.
##############################################################################


##############################################################################
# UPLOADING FILES AND RUNNING SETUP COMMANDS
#   Upload files, append to configs, create directories, and run setup
#   commands on agent hosts during creation or via re-provisioning.
##############################################################################


##############################################################################
# TROUBLESHOOTING
#   Common problems and how to fix them. Debugging with logs, verbose
#   output, and exec. What to do when agents crash or hosts won't start.
##############################################################################


##############################################################################
# TIPS AND TRICKS
#   Power-user shortcuts, lesser-known features, and workflow patterns
#   that make working with mng faster and more pleasant.
##############################################################################

