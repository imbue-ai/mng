# mngr connect - CLI Options Reference

Connects to an agent via the terminal.

This attaches to the agent's tmux session, roughly equivalent to SSH'ing into the agent's machine and attaching to the tmux session. Use `mngr open` to open an agent's URLs in a web browser instead.

Both modes track activity to understand when the agent should be considered idle.

**Alias:** `conn`

## Usage

```
mngr connect [[--agent] AGENT]
```

The agent can be specified as a positional argument for convenience. The following are equivalent:

```
mngr connect my-agent
mngr connect --agent my-agent
```

## General

- `--agent AGENT`: The agent to connect to. A positional argument is also accepted as a shorthand. If not specified, connects to the most recently created agent.
- `--[no-]start`: Automatically start the agent if it is currently stopped [default: start]

## Options

- `--[no-]reconnect`: Automatically reconnect if the connection is dropped [default: reconnect]
- `--message TEXT`: The initial message to send after the agent starts
- `--message-file PATH`: File containing the initial message to send
- `--message-delay SECONDS`: Seconds to wait before sending initial message [default: 1.0]
- `--retry N`: Number of times to retry connection on failure [default: 3]
- `--retry-delay DURATION`: Delay between connection retries (e.g., `5s`, `1m`) [default: 5s]
- `--attach-command TEXT`: Command to run instead of attaching to the agent's main session

## TODOs

The following features are not yet implemented:

- **Alias `conn`**: Not registered in CLI
- **`--message`**: Raises NotImplementedError
- **`--message-file`**: Raises NotImplementedError
- **`--message-delay`**: Only default value (1.0) works; custom values raise NotImplementedError
- **`--retry`**: Only default value (3) works; custom values raise NotImplementedError
- **`--retry-delay`**: Only default value (5s) works; custom values raise NotImplementedError
- **`--attach-command`**: Raises NotImplementedError
- **`--no-reconnect`**: Raises NotImplementedError (only `--reconnect` is supported)
- **Remote agent connections**: Only local agents supported; remote agents raise NotImplementedError
- **Default to most recently created agent**: Currently shows interactive selector instead when no agent specified
