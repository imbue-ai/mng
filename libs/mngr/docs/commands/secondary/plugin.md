# mngr plugin [future] - CLI Options Reference

Manage available and active plugins.

**Alias:** `plug`

## Usage

```
mngr plugin [ls|list|add|rm|remove|enable|disable] [options]
```

## General

- `--all`: Select all available plugins [default]
- `--active`: Select only currently enabled plugins

## ls, list

- `--format FORMAT`: Output format [default: `human`, choices: `human`, `json`, `jsonl`]. Mutually exclusive with `--json` and `--jsonl` (see [common options](../generic/common.md))
- `--fields FIELDS`: Which fields to include (comma-separated). Available: `name`, `version`, `description`, `enabled`
