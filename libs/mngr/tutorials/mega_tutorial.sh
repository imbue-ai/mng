#!/bin/bash
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

# TODO: create all of the rest of the *section* headers, like we did for create and list




