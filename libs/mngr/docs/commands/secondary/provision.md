# mngr provision - CLI Options Reference

Ensures that an agent has the required packages, libraries, environment variables, and configuration files to run properly.

These are mostly specified via plugins, but custom provisioning steps can also be defined using the options below.

Provisioning is done per agent, but obviously any changes from one agent will be visible to other agents on the same host.
Be careful to avoid conflicts when provisioning multiple agents on the same host.

**Alias:** `prov`

## Usage

```
mngr provision [[--agent] agent]
```

## General

- `--bootstrap / --bootstrap-and-warn / --no-bootstrap`: Whether to auto-install any required tools that are missing [default: `--bootstrap-and-warn` on remote hosts, `--no-bootstrap` on local]
- `--[no-]destroy-on-fail`: Destroy the host if provisioning fails [default: no]

## Simple configuration

- `--user-command TEXT`: Run a custom shell command during provisioning [repeatable]
- `--sudo-command TEXT`: Run a custom shell command during provisioning as root [repeatable]
- `--upload-file LOCAL:REMOTE`: Upload a local file to the agent at the specified remote path [repeatable]
- `--env KEY=VALUE`: Set an environment variable KEY=VALUE on the agent [repeatable]
- `--pass-env KEY`: Forward an environment variable from your current shell to the agent [repeatable]
- `--append-to-file REMOTE:TEXT`: Append TEXT to a file on the agent at the specified remote path [repeatable]
- `--prepend-to-file REMOTE:TEXT`: Prepend TEXT to a file on the agent at the specified remote path [repeatable]
- `--create-directory REMOTE`: Create a directory on the agent at the specified remote path [repeatable]
