# Provisioning Spec

This document describes implementation details for the provisioning system. For user-facing documentation, see [provisioning concepts](../docs/concepts/provisioning.md).

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
