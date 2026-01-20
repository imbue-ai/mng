# mngr cleanup - CLI Options Reference

Destroy or stop agents and hosts in order to free up resources.

When running in a pty, defaults to providing an interactive interface for reviewing running agents and hosts and selecting which ones to destroy or stop.

When running in a non-interactive setting (or if `--yes` or `--no-interactive` is provided), will destroy all selected agents/hosts without prompting.

For automatic garbage collection of unused resources without interaction, see `mngr gc`.

**Alias:** `clean`

## Usage

```
mngr cleanup
```

## General

- `-f, --force, --yes`: Skip confirmation prompts
- `--dry-run`: Show what would be destroyed or stopped without executing

## Filtering

- `--include FILTER`: Include only agents/hosts matching this filter
- `--exclude FILTER`: Exclude agents/hosts matching this filter
- `--older-than DURATION`: Select agents/hosts older than specified (e.g., `7d`, `24h`)
- `--idle-for DURATION`: Select agents idle for at least this duration
- `--tag TAG`: Select agents/hosts with this tag [repeatable]
- `--provider PROVIDER`: Select hosts from this provider [repeatable]
- `--agent-type AGENT`: Select this agent type (e.g., `claude`, `codex`) [repeatable]

## Actions

- `--destroy`: Destroy selected agents/hosts (default)
- `--stop`: Stop selected agents/hosts instead of destroying
- `--snapshot-before`: Create snapshots before destroying or stopping. When destroying, only makes sense with --keep-snapshots

## Resource Cleanup

See [resource cleanup options](../generic/resource_cleanup.md) to control which associated resources are also destroyed (defaults to all).
