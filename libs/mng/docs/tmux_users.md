# For tmux users

## Nested tmux

Mng runs your agents in tmux sessions.
If you already use tmux to run `mng` itself,
by default, `mng` won't be able to drop you into the agents' tmux sessions,
because `tmux` refuses to run inside `tmux` by default.

There are two approaches to solve this:

- If you prefer to keep the agents' tmux sessions outside the session where you run `mng`,
  you can use an alternative `connect-command` to the `create` and `start` subcommands,
  which can, for example, open a new terminal tab and connect to the agent session from there.

  In particular, if you use iTerms2, there's a builtin plugin to do that for you -
  run `mng plugin list` to see it.

- You can tell `mng` to allow nested tmux -
  it should have printed a command to do so.

When using nested tmux,
you'll need some configuration to make the keybindings work for both the "outside" and "inside" sessions.
There are several approaches:

- In tmux's default binding,
  pressing `Ctrl-B` twice sends `Ctrl-B` to the program running inside tmux.

  This means you can use all your prefixed keybindings simply by pressing an extra `Ctrl-B` every time.

- You can also configure an alternative keybinding for tmux sessions created by `mng`,
  by editing `~/.mng/tmux.conf`.

- A slightly more advanced approach is to have a key that swaps the outer tmux's key table,
  effectively making it switch between which layer of tmux you want to operate on.
  For example, to use F12 for this purpose, put the following in your `~/.tmux.conf`:

  ```
  bind -T root F12  \
    set prefix None \;\
    set key-table off \;\
    set status-style "fg=colour245,bg=colour238" \;\
    refresh-client -S

  bind -T off F12 \
    set -u prefix \;\
    set -u key-table \;\
    set -u status-style \;\
    refresh-client -S
  ```

You can find other approaches by searching for "nested tmux" or "tmux in tmux".

## Isolating mng's tmux sessions

By default, `mng` runs local agent tmux sessions on a dedicated server socket named `mng` (via `tmux -L mng`). This means `mng`'s sessions are isolated from your personal tmux sessions -- they won't show up in `tmux ls` and won't cause nested tmux issues.

To interact with `mng`'s tmux sessions directly, use:

```bash
tmux -L mng ls           # list mng's sessions
tmux -L mng attach -t <session>  # attach to a specific session
```

If you prefer `mng`'s sessions to share your global tmux server (the pre-isolation behavior), set `local_tmux_server_socket_name` to `"default"` in your settings:

```toml
# In ~/.mng/profiles/<profile>/settings.toml or .mng/settings.toml
local_tmux_server_socket_name = "default"
```

You can also set it to any other name to use a custom socket.
