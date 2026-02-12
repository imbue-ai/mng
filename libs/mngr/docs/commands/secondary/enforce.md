# mngr enforce - CLI Options Reference

Ensure that no hosts have exceeded their idle timeouts, etc.

In order to ensure that *untrusted* hosts cannot exceed their idle timeout, this command must be run periodically.
It also helps ensure that no hosts have become stuck during state transitions (building, starting, stopping, etc.)

This command should be run from a single location, and should be aware of *all* valid state signing keys.

## Usage

```
mngr enforce [OPTIONS]
```

## Checks

- `--[no-]check-idle`: Check for hosts that have exceeded their idle timeouts [default: check-idle]
- `--[no-]check-timeouts`: Check for hosts stuck in transitory states (building, starting, stopping) [default: check-timeouts]

## Timeout Configuration

- `--building-timeout SECONDS`: Seconds before a BUILDING host is considered stuck [default: 1800]
- `--starting-timeout SECONDS`: Seconds before a STARTING host is considered stuck [default: 900]
- `--stopping-timeout SECONDS`: Seconds before a STOPPING host is considered stuck [default: 600]

## Scope

- `--all-providers`: Enforce across all providers
- `--provider NAME`: Enforce for a specific provider (repeatable)

## Safety

- `--dry-run`: Show what would be enforced without taking action
- `--on-error (abort|continue)`: What to do when errors occur [default: abort]
- `-w, --watch SECONDS`: Re-run enforcement checks at the specified interval

## Examples

Preview what would be enforced:
```
mngr enforce --dry-run
```

Check only idle hosts:
```
mngr enforce --check-idle --no-check-timeouts
```

Run enforcement every 5 minutes:
```
mngr enforce --watch 300
```

Custom timeout for starting hosts on a specific provider:
```
mngr enforce --starting-timeout 1200 --provider docker
```
