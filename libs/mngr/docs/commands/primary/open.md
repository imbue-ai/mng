# mngr open - CLI Options Reference

Opens a URL associated with an agent in a web browser.

Agents can have a variety of different URLs associated with them. If the URL type is unspecified (and there is more than one URL), this command opens a little TUI that lets you pick from the available URLs.

Use `mngr connect` to attach to an agent via the terminal instead.

## Usage

```
mngr open [[--agent] AGENT] [[--type] URL_TYPE]
```

The agent and url type can be specified as positional arguments for convenience. The following are equivalent:

```
mngr open my-agent terminal
mngr open --agent my-agent --type terminal
```

## General

- `--agent AGENT`: The agent to open. A positional argument is also accepted as a shorthand. If not specified, opens the most recently created agent.
- `-t, --type URL_TYPE`: The type of URL to open (e.g., `chat`, `terminal`, `diff`, etc.). If not specified, and there are multiple URL types, a TUI will be shown to select from the available URLs.
- `--[no-]start`: Automatically start the agent if it is currently stopped [default: start]

## Options

- `--[no-]wait`: Wait for the browser to be closed before exiting [default: no-wait]
- `--active`: Continually update the active timestamp while connected (prevents idle shutdown). Only makes sense with `--wait`

## TODO

The `open` command is not yet implemented. Missing functionality:
- Core command implementation and CLI registration
- URL opening functionality (browser integration)
- TUI selector for multiple URL types
- `--agent` option support (positional and flag)
- `--type` option support (positional and flag)
- `--[no-]start` option (auto-start stopped agents)
- `--[no-]wait` option (wait for browser close)
- `--active` option (update timestamp while waiting)
