# Codex CLI Agent Type

The Codex agent type enables running [OpenAI's Codex CLI](https://github.com/openai/codex) coding assistant through `mngr`.

## Overview

Codex is a CLI-based AI coding assistant. The codex agent type provides basic integration to run Codex as a managed agent with tmux sessions and standard agent lifecycle management.

## Current Implementation

The codex agent type currently provides:

- **Agent type registration**: Registered as a built-in agent type with command `"codex"`
- **Basic lifecycle management**: Runs in tmux sessions with standard agent state tracking
- **Command execution**: Uses the `codex` command (assumes it's already installed)
- **Standard agent features** (via `BaseAgent`):
  - Permission management
  - Status and activity reporting
  - Message sending via stdin
  - Plugin data storage
  - Environment variable management
  - Lifecycle state tracking (stopped, running, done, replaced)

## Usage

Create a codex agent:

```bash
mngr create my-codex codex
```

The agent runs the `codex` command in a tmux session. You can pass additional arguments:

```bash
mngr create my-codex codex -- --model <model-name>
```

## Requirements

The codex agent type assumes:

- **Codex CLI is pre-installed**: The `codex` command must be available in PATH
- **API credentials configured**: Any required API keys or credentials must be set up manually
- **No automatic setup**: No provisioning or installation logic is provided

## Configuration

The `CodexAgentConfig` class provides only the basic `command` field:

```toml
[agent_types.my_codex]
command = "codex"
cli_args = "--model code-davinci-002"
```

## Limitations

Unlike the `claude` agent type, codex does not provide:

- Session resumption support
- Automatic installation or validation
- Settings or credentials synchronization
- Configuration file management
- Provisioning hooks

## TODOs

The following features are not yet implemented for the codex agent type:

- **Custom agent class**: No `CodexAgent` class; uses `BaseAgent` with default implementations
- **Session resumption**: No support for resuming previous sessions (unlike claude)
- **Installation checking**: No validation that codex is installed before starting
- **Automatic installation**: No provisioning logic to install codex on remote hosts
- **API key validation**: No checks for required credentials or API keys
- **Settings synchronization**: No syncing of codex configuration files to remote hosts
- **Credentials synchronization**: No credential transfer for remote agents
- **Configuration options**: No agent-specific config beyond basic `command` field (no `check_installation`, `sync_settings`, etc.)
- **Provisioning hooks**: No `on_before_provisioning()`, `provision()`, or `get_provision_file_transfers()` implementations
- **Comprehensive tests**: Only 1 basic test exists (default command check)
- **Documentation**: No provisioning guide or configuration reference
