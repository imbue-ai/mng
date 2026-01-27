# Logging Spec

How mngr handles logging and output.

## Design Philosophy

mngr separates three distinct concerns:
1. **Command Results**: Structured data output (to stdout)
2. **Console Logging**: Diagnostic information shown during execution (to stderr)
3. **File Logging**: Persistent diagnostic logs for debugging (to `~/.mngr/logs/`)

## Command Results vs Logging

**Command Results** are the primary output of a command (e.g., agent ID, status):
- Sent to stdout
- Format controlled by `--format` flag (human, json, jsonl)
- Suppressed by `-q/--quiet`

**Console Logging** shows what's happening during execution:
- Sent to stderr
- Level controlled by `-v/--verbose` flags or config
- Shows: BUILD (default), DEBUG (-v), TRACE (-vv)
- BUILD level shows image build logs (modal, docker) in medium gray
- DEBUG level shows diagnostic messages in blue
- Suppressed by `-q/--quiet`

**File Logging** captures detailed diagnostic information:
- Saved to `~/.mngr/logs/<timestamp>-<pid>.json`
- Structured JSON format for easy parsing
- Level controlled by config (default: DEBUG)
- Includes: timestamp, command, args, execution trace, errors

## Configuration

Logging behavior is configured via the `[logging]` section in config files:

```toml
[logging]
# What gets logged to file (default: DEBUG)
file_level = "DEBUG"

# What gets shown on console during commands (default: BUILD)
# BUILD shows image build logs (modal, docker) in medium gray
console_level = "BUILD"

# Where logs are stored (relative to data root if relative)
log_dir = "logs"

# Maximum number of log files to keep
max_log_files = 1000

# Maximum size of each log file before rotation
max_log_size_mb = 10

# Whether to log what commands were executed
is_logging_commands = true

# Whether to log stdout/stderr from executed commands
is_logging_command_output = false

# Whether to log environment variables (security risk)
is_logging_env_vars = false
```

## CLI Options

CLI flags override config settings:

- `--format [human|json|jsonl]`: Output format for command results
- `-q, --quiet`: Suppress all console output
- `-v, --verbose`: Show DEBUG on console
- `-vv, --very-verbose`: Show TRACE on console
- `--[no-]log-commands`: Override is_logging_commands
- `--[no-]log-command-output`: Override is_logging_command_output
- `--[no-]log-env-vars`: Override is_logging_env_vars (security risk)

## Log File Management

### Location

Logs are stored at:
- `~/.mngr/logs/` by default
- Configurable via `logging.log_dir` in config
- If relative, resolved relative to data root (`default_host_dir` or `~/.mngr`)

### Naming

Log files are named: `<timestamp>-<pid>.json`
- Example: `20231215-143022-12345.json`
- Timestamp: YYYYMMDD-HHMMSS
- PID: Process ID of the mngr invocation

### Rotation

Logs are rotated based on two criteria:
1. **Size**: When a log file exceeds `max_log_size_mb`, it's rotated
2. **Count**: When total files exceed `max_log_files`, oldest are removed

Oldest logs are identified by least-recently-modified time.

### Format

Logs are structured JSON (one JSON object per line) containing:
- `timestamp`: ISO 8601 timestamp
- `level`: Log level (TRACE, DEBUG, BUILD, INFO, WARN, ERROR)
- `message`: Log message
- `name`: Logger name (module)
- `function`: Function name
- Additional context fields as needed

## Sensitive Data

### Environment Variable Redaction

Environment variables are **redacted from logs by default** for security. This prevents accidental leakage of:
- API keys or tokens
- SSH private keys
- Passwords
- Other credentials passed via `--pass-env` or `--env`

To include environment variables in logs (e.g., for debugging), use `--log-env-vars` or set `is_logging_env_vars = true` in config. This is a security risk and should only be enabled when necessary.

### Command Output Logging

Command output logging (`is_logging_command_output`) is also disabled by default to prevent accidental leakage of sensitive data that might appear in stdout/stderr.

## TODOs

The following features are specified but not yet implemented:

- **Command execution logging**: The `is_logging_commands` flag is defined but not used. No code actually logs what commands are executed during mngr operations.
- **Command output logging**: The `is_logging_command_output` flag is defined but not used. Command stdout/stderr is not captured or logged to files.
- **Environment variable logging**: The `is_logging_env_vars` flag is defined but not used. Environment variables passed to commands are not logged.
- **Sensitive data redaction**: No code exists to mask/redact API keys, tokens, passwords, or other credentials in logs.
