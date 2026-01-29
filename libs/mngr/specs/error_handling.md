# Error Handling Spec

How mngr handles errors across commands.

## General Principles

- Errors result in non-zero exit codes and clear error messages
- The CLI should clearly state *why* it failed (and ideally what to do about it)
- The user story for recovery is usually "fix the problem and try again" (standard CLI behavior)

## Error Classification

All errors are one of these four types:

- **Expected transient** [future]: Inherits from TransientMngrError. Is retriable
- **Expected plugin**: Inherits from PluginMngrError. Never retried. Disables the plugin that raised this.
- **Expected agent** [future]: Inherits from AgentMngrError. Never retried. Fails the agent that raised this.
- **Expected host** [future]: Inherits from HostMngrError. Never retried. Fails the host that raised this.
- **Expected fatal** [future]: Inherits from FatalMngrError. Never retried. Fail the entire command immediately.
- **Unexpected**: All other errors. Retry behavior depends on configuration.

## Retry Behavior

- Transient errors are retried according to configuration [future]
- PluginMngrError, AgentMngrError, and/or HostMngrError are either warnings or errors, depending on configuration

## Configuration

There is a hierarchy of error configuration:

- Overall defaults
- Plugin defaults
- Separate defaults for write and read commands [future] (that override the overall defaults)
- Per-command overrides (that override the read/write defaults)
- Per-command, per-plugin overrides [future] (that override all of the above)

What can be configured [future]:
- Number of retries
- Back-off exponent, strategy, etc.
- Whether to treat PluginMngrError, AgentMngrError, and/or HostMngrError as warnings or errors
