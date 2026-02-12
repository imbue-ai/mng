# mngr schedule

**Synopsis:**

```text
mngr schedule <subcommand> [OPTIONS]
```

Manage cron-based schedules that periodically run `mngr create` to spin up agents.

## mngr schedule add

Add a new scheduled agent. Installs a crontab entry that runs `mngr create`
on the specified schedule.

**Usage:**

```text
mngr schedule add [OPTIONS] MESSAGE [CREATE_ARGS]...
```

**Arguments:**

| Name | Description |
|------|-------------|
| `MESSAGE` | Initial message to send to the created agent |
| `CREATE_ARGS` | Additional arguments passed through to `mngr create` |

**Options:**

| Name | Type | Description | Required |
|------|------|-------------|----------|
| `--name` | text | Name for this schedule (must be unique) | Yes |
| `--cron` | text | Cron expression (e.g., `0 * * * *` for hourly) | Yes |
| `--template` | text | Create template to use | No |

## mngr schedule list

List all configured schedules.

**Usage:**

```text
mngr schedule list [OPTIONS]
```

## mngr schedule remove

Remove a schedule and its crontab entry.

**Usage:**

```text
mngr schedule remove [OPTIONS] NAME
```

**Arguments:**

| Name | Description |
|------|-------------|
| `NAME` | Name of the schedule to remove |

## mngr schedule run

Run a schedule immediately without waiting for the next cron trigger.

**Usage:**

```text
mngr schedule run [OPTIONS] NAME
```

**Arguments:**

| Name | Description |
|------|-------------|
| `NAME` | Name of the schedule to run |

## Examples

**Add an hourly schedule using a template:**

```bash
$ mngr schedule add --cron "0 * * * *" --template my-daily-hook "look at flaky tests and fix one" --name flaky-fixer
```

**Add a weekday morning schedule:**

```bash
$ mngr schedule add --cron "0 9 * * 1-5" "review open PRs and leave comments" --name pr-reviewer
```

**List all schedules:**

```bash
$ mngr schedule list
```

**List schedules in JSON format:**

```bash
$ mngr schedule list --format json
```

**Remove a schedule:**

```bash
$ mngr schedule remove flaky-fixer
```

**Run a schedule immediately:**

```bash
$ mngr schedule run flaky-fixer
```

## How it works

Schedules are stored in `~/.mngr/profiles/<id>/schedules.toml` and executed
via the system crontab (`crontab -l` / `crontab -`). Each schedule installs a
crontab entry that runs `mngr create` with the specified arguments.

The crontab entry includes a marker comment (`# mngr-schedule:<name>`) for
reliable identification when removing schedules.

Output from scheduled runs is logged to `~/.mngr/logs/schedule-<name>.log`.

## See Also

- [mngr create](../primary/create.md) - Create a new agent
- [mngr config](config.md) - Configure create templates used by schedules
