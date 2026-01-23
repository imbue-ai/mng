# Claude Code Agent

The `claude` agent type provides integration with [Claude Code](https://claude.ai/claude-code), Anthropic's agentic coding tool.

## Configuration

The Claude agent type supports the following configuration options:

- `command`: Command to run claude agent (default: `"claude"`)
- `sync_home_settings`: Whether to sync Claude settings from `~/.claude/` to a remote host (default: `true`)
- `sync_claude_json`: Whether to sync the local `~/.claude.json` to a remote host for API key settings and permissions (default: `true`)
- `sync_repo_settings`: Whether to sync unversioned `.claude/` settings from the repo to the agent work_dir (default: `true`)
- `sync_claude_credentials`: Whether to sync `~/.claude/.credentials.json` to a remote host (default: `true`)
- `override_settings_folder`: Extra folder to sync to the repo `.claude/` folder in the agent work_dir (default: `None`)
- `check_installation`: Check if claude is installed (default: `true`)

## Features

### Session Resumption

The agent automatically creates commands with session resumption support. Each agent gets a stable UUID, and the command is formatted as:

```bash
claude --resume UUID args || claude --session-id UUID args
```

This allows users to hit 'up' and 'enter' in tmux to resume an existing session or create it if it doesn't exist.

### Automatic Installation

For remote hosts, Claude will be automatically installed if not present using the official installer:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

For local hosts, the user is prompted for consent before installation.

### Settings Synchronization

When using remote hosts, the following files and directories are automatically synchronized:

- `~/.claude/settings.json`
- `~/.claude/skills/`
- `~/.claude/agents/`
- `~/.claude/commands/`
- `~/.claude.json`
- `~/.claude/.credentials.json`

Repo-local settings (files matching `.claude/*.local.*`) are also transferred to maintain project-specific configuration.

### Environment Variables

The agent sets:
- `MAIN_CLAUDE_SESSION_ID`: Set to the agent's UUID for session tracking
- `IS_SANDBOX`: Set to `1` for remote hosts (not set for local hosts)

## TODOs

The following features are referenced in the code but not yet implemented:

- **API key validation**: Check that either an API key exists in the environment or credentials will be synced before provisioning (see claude_agent.py:161)
- **Interactive mode detection**: Installation prompts need to understand whether mngr is running in interactive mode, should be part of MngrContext (see claude_agent.py:223)
- **Automatic installation configuration**: For remote hosts, check whether the user has configured automatic installation preference before installing (see claude_agent.py:230)
