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

# TODO: add tons more examples of useful flags for create, like:
#  --build-arg to specify custom Dockerfiles for Modal
#  --host to specify which host to run on (ex: if you have multiple Modal
#  ...basically each of the option for mngr create (don't bother giving multiple examples for the same concept though, just mention the alternative arg, like I did for initial message passing above)

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
#   Some agents expose web interfaces. "mngr open" launches them in your
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
#   List, enable, and disable plugins that extend mngr with new agent types,
#   provider backends, and CLI commands.
##############################################################################


##############################################################################
# CONFIGURATION
#   Customize mngr's behavior via configuration files. Set defaults for
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
#   run mngr from). Use projects to organize agents and filter your list.
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
#   Pass environment variables to agents during creation, control mngr
#   behavior via env vars, and understand the variables mngr sets for you.
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
#   Use mngr in shell scripts, CI pipelines, and cron jobs. JSON output,
#   headless mode, idempotent creation, and programmatic control.
##############################################################################


##############################################################################
# OUTPUT FORMATS AND MACHINE-READABLE OUTPUT
#   Switch between human-readable, JSON, and JSONL output. Use --format
#   with templates, pipe output to jq, and build tooling on top of mngr.
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
#   that make working with mngr faster and more pleasant.
##############################################################################

