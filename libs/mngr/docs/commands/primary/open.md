# mngr open - CLI Options Reference

Opens a URL associated with an agent in a web browser.

Agents can have a variety of different URLs associated with them. If the URL type is unspecified (and there is more than one URL), this command opens a little TUI that lets you pick from the available URLs [future].

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
- `-t, --type URL_TYPE` [future]: The type of URL to open (e.g., `chat`, `terminal`, `diff`, etc.). If not specified, and there are multiple URL types, a TUI will be shown to select from the available URLs.
- `--[no-]start`: Automatically start the agent if it is currently stopped [default: start]

## Options

- `--[no-]wait`: Keep running after opening (press Ctrl+C to exit) [default: no-wait]
- `--active`: Continually update the active timestamp while connected (prevents idle shutdown). Only makes sense with `--wait`
