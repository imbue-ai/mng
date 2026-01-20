When relevant, the last user input time is tracked via:
- Keystrokes sent when running `mngr connect` (terminal)
- Mouse/keyboard events via injected JS (when accessing an agent via the web with default plugins that run `ttyd` and configure `nginx` to inject the script)

When relevant, the last agent output time is tracked by writing to an activity file (self-reporting, configured by default for most agents). See [agent conventions](./conventions.md#Activity-Reporting) for details.

In practice, the activity is recorded by outputting `date` to a file whenever there is activity, and the idle script simply checks the modification time of that file.
