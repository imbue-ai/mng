When provisioning locally, the default is --no-bootstrap to avoid unexpected changes to the host system.
However, this is probably kind of annoying, so it should ideally output a set of commands that can be easily run by a user to fix any missing dependencies or install any packages.

## Provisioning Errors

**During initial provisioning (`mngr create`):**
- Errors that cause the command to fail and host transitions to "destroyed" state
- Warnings are logged but creation continues

**During re-provisioning (`mngr provision`):**
- Errors cause the command to fail but do not affect agent state
- Unless `--destroy-on-fail` is set, in which case the host is destroyed
- Warnings are logged but provisioning continues

## TODOs

The following functionality described above is **not yet implemented**:

- [ ] `mngr provision` command for re-provisioning existing agents
- [ ] `--no-bootstrap` flag to avoid unexpected changes to host system during local provisioning
- [ ] Output commands for users to manually install missing dependencies/packages
- [ ] Host transition to "destroyed" state when `mngr create` provisioning fails
- [ ] `--destroy-on-fail` flag for `mngr provision` command
- [ ] Warning mode that logs warnings but continues provisioning (currently all errors fail immediately)
