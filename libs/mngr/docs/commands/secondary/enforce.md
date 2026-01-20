# mngr enforce - CLI Options Reference

Ensure that no hosts have exceeded their idle timeouts, etc.

In order to ensure that *untrusted* hosts cannot exceed their idle timeout, this command must be periodically.
It also helps ensure that no hosts have become stuck during state transitions (building, starting, stopping, etc.)

This command should be run from a single location, and should be aware of *all* valid state signing keys.

## Usage

```
mngr enforce
```

## General

- `--[no-]check-idle`: Check for hosts that have exceeded their timeouts [default: check-idle]
- `--[no-]check-timeouts`: Check for hosts that have exceeded their timeouts for some (transitory) state. See the config for more details. [default: check-timeouts]
- `-w, --watch SECONDS`: Re-run enforcement checks at the specified interval
