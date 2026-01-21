# Provisioning Spec

This document describes implementation details for the provisioning system. For user-facing documentation, see [provisioning concepts](../docs/concepts/provisioning.md).

## Pre-Provisioning Validation Hook

Before any provisioning steps run, mngr invokes the `before_provision_agent` hook. This hook allows plugins to validate that required preconditions are met before any actual provisioning work begins. This is the appropriate place to check for:

- Required environment variables (e.g., API keys, credentials)
- Required local files or directories
- Network connectivity to required services
- Proper authentication/authorization state

If a plugin's validation fails, it should raise a `FatalMngrError` with a clear message explaining what is missing and how to fix it. This ensures that provisioning fails fast with actionable error messages rather than failing partway through after already making changes.

**Important**: The `before_provision_agent` hook runs *before* any file transfers or package installations. It should only perform read-only validation checks, not make any changes to the host.

Example validations a plugin might perform:
- Check that `ANTHROPIC_API_KEY` is set for the claude plugin
- Check that required SSH keys exist locally
- Verify that a config file template exists at the expected path

## File Transfer Collection

Plugins can declare files and folders that need to be transferred from the local machine to the remote host during provisioning. This is done via a `get_provision_file_transfers` hook that returns a list of transfer specifications.

Each transfer specification includes:

| Field | Type | Description |
|-------|------|-------------|
| `local_path` | `Path` | Path to the file or directory on the local machine |
| `remote_path` | `Path` | Destination path on the remote host |
| `is_required` | `bool` | If `True`, provisioning fails if the local file doesn't exist. If `False`, the transfer is skipped if the file is missing. |

```python
class FileTransferSpec(FrozenModel):
    """Specification for a file to transfer during provisioning."""

    local_path: Path = Field(description="Path to the file/directory on the local machine")
    remote_path: Path = Field(description="Destination path on the remote host")
    is_required: bool = Field(
        default=True,
        description="Whether provisioning should fail if the local file doesn't exist",
    )
```

### Collection and Execution Order

1. **Collection phase**: Before provisioning begins, mngr calls `get_provision_file_transfers()` on each enabled plugin to collect all file transfer requests.

2. **Validation phase**: For each transfer where `is_required=True`, mngr verifies that `local_path` exists. If any required file is missing, provisioning fails with a clear error listing all missing files.

3. **Transfer phase**: All collected transfers are executed, with optional transfers (where `is_required=False`) skipped if their source doesn't exist. Transfers happen *before* package installation and other provisioning steps.

### Use Cases

- **Config files**: Transfer local config files like `~/.anthropic/config.json` or `~/.npmrc`
- **Credentials**: Transfer credential files (subject to permission checks)
- **Project-specific files**: Transfer files referenced in `.mngr/settings.toml` that aren't part of the work_dir
- **Plugin state**: Transfer plugin-specific state that needs to be present for the agent to function

### Deduplication

If multiple plugins request the same `remote_path`, mngr should detect this and either:
- Error if the `local_path` values differ (conflicting transfers)
- Deduplicate if the `local_path` values are identical (same transfer requested multiple times)

## Package Version Requirements

Plugins should check both for the presence of required packages AND for minimum version requirements. This ensures that provisioning fails early with clear errors rather than allowing agents to start with incompatible package versions.

Version checks should happen before any installation attempts, and error messages should clearly indicate:
- Which package is missing or too old
- The minimum required version
- The currently installed version (if any)

## Cross-Platform Package Installation

mngr should provide helper functions for cross-platform package installation that plugins can use. These helpers should:

1. **Detect the platform**: Identify whether the host is using apt, yum, brew, etc.
2. **Batch package operations**: Collect all package requests from all plugins before executing any installations
3. **Handle conflicts intelligently**: Detect version conflicts between plugins and resolve or error appropriately
4. **Make suggestions for local hosts**: On local hosts, suggest commands to the user rather than attempting installation

### Batched Installation

Rather than each plugin defining all pyinfra operations itself, plugins should be given a chance to declare their basic requirements (packages, versions, etc.) first. mngr can then:

1. Collect all requirements from all plugins
2. Resolve version constraints
3. Batch installation commands (e.g., a single `apt-get install` with all packages)
4. Execute the batched operations in parallel where possible

This approach handles the 80/20 case efficiently and avoids:
- Sequential installation of packages (slow)
- Package manager conflicts from multiple concurrent operations
- Redundant invocations of package managers

### Serial Agent Provisioning

Beyond the basic package installation helpers, agents and their plugins must be provisioned serially on a given machine to avoid race conditions. This is necessary because:
- Plugins may modify shared system state
- Multiple plugins may need to configure the same service (e.g., nginx)
- File writes to shared locations must be coordinated

**Open Question**: Could we have a `get_provisioning_dependencies()` hook that allows plugins to declare their dependencies on each other? This would enable some parallelization while maintaining correctness. (This relates to the plugin ordering question discussed in the plugin spec.)

## Interaction with the Local Provider

When running locally, plugins should detect whether the required packages are present, and if they are not, simply error. They can suggest some commands for installing the packages (and versions) that they want, but they should not install any dependencies automatically on your local machine (it generally requires sudo anyway).
