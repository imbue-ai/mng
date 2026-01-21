# Provisioning Spec

This document describes implementation details for the plugin provisioning system. For user-facing documentation, see [provisioning concepts](../docs/concepts/provisioning.md).

## Pre-Provisioning Validation Hook

Before any provisioning steps run, mngr invokes the `on_before_agent_provisioning` hook. This hook allows plugins to validate that required preconditions are met before any actual provisioning work begins.

Example validations a plugin might perform:
- Check that `ANTHROPIC_API_KEY` is set for the claude plugin
- Check that required SSH keys exist locally
- Verify that a config file template exists at the expected path

If a plugin's validation fails, it should raise a `PluginMngrError` with a clear message explaining what is missing and how to fix it. This ensures that provisioning fails fast with actionable error messages rather than failing partway through after already making changes.

**Important**: The `on_before_agent_provisioning` hook runs *before* any file transfers or package installations. It should only perform read-only validation checks, not make any changes to the host.

## File Transfer Collection

The next hook to be called is the `get_provision_file_transfers` hook.

Plugins can declare files and folders that need to be transferred from the local machine to the remote host during provisioning by returning a list of transfer specifications.

Each transfer specification includes:

| Field | Type | Description |
|-------|------|-------------|
| `local_path` | `Path` | Path to the file or directory on the local machine |
| `remote_path` | `Path` | Destination path on the remote host. Relative paths will be relative to the agent's work_dir |
| `is_required` | `bool` | If `True`, provisioning fails if the local file doesn't exist. If `False`, the transfer is skipped if the file is missing. |

### Collection and Execution Order

1. **Collection phase**: Before provisioning begins, mngr calls `get_provision_file_transfers()` on each enabled plugin to collect all file transfer requests.
2. **Validation phase**: For each transfer where `is_required=True`, mngr verifies that `local_path` exists. If any required file is missing, provisioning fails with a clear error listing all missing files.
3. **Transfer phase**: All collected transfers are executed, with optional transfers (where `is_required=False`) skipped if their source doesn't exist. Transfers happen *before* package installation and other provisioning steps.

### Use Cases

- **Config files**: Transfer local config files like `~/.anthropic/config.json` or `~/.npmrc`
- **Credentials**: Transfer credential files (subject to permission checks)
- **Project-specific files**: Transfer files referenced in `.mngr/settings.toml` that aren't part of the work_dir
- **Plugin state**: Transfer plugin-specific state that needs to be present for the agent to function

Plugins should provide configuration options for selecting which files to transfer.

### Deduplication

If multiple plugins request the same `remote_path`, the later plugin wins.

## Agent provisioning

The next hook called is the main `provision_agent` hook.

This is where plugins should check both for the presence of required packages and, ideally, minimum version requirements (which helps prevent downstream failures that are harder to debug).

If a package is missing (or too old), plugins should emit a warning, and then:

1. For remote hosts: attempt to install it
2. For local hosts: present the user with a command that can be run to either install it (if possible), or that they can run to install it themselves (if, eg, root access is required)

Plugins should generally allow configuration for:

1. Disabling any kind of checking for packages (eg, assume they are properly installed)
2. Disabling automatic installation of missing packages (eg, just emit a message and the install command and fail)

The default behavior is intended to make `mngr` more usable--this way if something fails, the plugin can automatically fix it (rather than forcing the user to debug missing dependencies themselves).

Plugins can use pyinfra's built-in package management support to handle cross-platform installation of packages, or just do it themselves.

## Post-Provisioning Hook

After all provisioning steps have completed, mngr invokes the `on_after_agent_provisioning` hook. This hook allows plugins to perform any finalization or verification steps after provisioning is done.
