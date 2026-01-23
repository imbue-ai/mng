# mngr config - CLI Options Reference

Configures mngr: list, get, set, unset, or edit various settings.

**Alias:** `cfg`

## Usage

```
mngr config [list|get|set|unset] [--scope [project|user]] [key] [value]
mngr config edit [--scope [project|user]]
```

## Notes

Much like a simpler version of `git config`, `mngr config` allows you to manage configuration settings at either the project or user level.

`mngr config edit` opens the config file in your default editor for manual editing.

Run `mngr help --config` for details on available keys and their meanings.

## TODOs

- **`mngr help --config`**: The command to list available configuration keys and their meanings is not yet implemented.
