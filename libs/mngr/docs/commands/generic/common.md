## Common Options

### Output Format

- `--format [human|json|jsonl|FORMAT]`: Output format for command results. If FORMAT, see below docs about template formatting [default: human]

Command results are sent to stdout. Console logging is sent to stderr.

### Console Logging

- `-q, --quiet`: Suppress all console output
- `-v, --verbose`: Show DEBUG level logs on console
- `-vv, --very-verbose`: Show TRACE level logs on console

### File Logging

Logs are automatically saved to `~/.mngr/logs/<timestamp>-<pid>.json` with rotation based on config settings.

- `--log-file PATH`: Override the log file path (e.g., `/tmp/mngr.log`)
- `--[no-]log-commands`: Log what commands were executed [default: from config]
- `--[no-]log-command-output`: Log stdout/stderr from executed commands [default: from config]
- `--[no-]log-env-vars`: Log environment variables (security risk, disabled by default)

Environment variables are redacted from logs by default for security. Use `--log-env-vars` to include them.

### Other Options

- `--context PATH`: Project context directory (used for build context and loading project-specific config) [default: local .git root]
- `--[no-]interactive`: Enable interactive mode (e.g. show a TUI or interactive prompts) [default: interactive if pty]
- `--plugin TEXT / --enable-plugin TEXT / --disable-plugin TEXT`: Enable / disable selected plugins

## TODOs

- **Custom format templates**: The `--format FORMAT` option for custom template strings is not implemented yet (raises NotImplementedError in cli/list.py:165-166)
- **--[no-]interactive as common option**: Currently only implemented in `create` command, not available as a common option across all commands
