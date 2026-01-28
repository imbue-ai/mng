# mngr gc

Garbage collect unused resources.

Automatically removes unused resources from providers and mngr itself.

Examples:

  mngr gc --work-dirs --dry-run

  mngr gc --all-agent-resources

  mngr gc --machines --snapshots --provider docker

  mngr gc --logs --build-cache

**Usage:**

```text
mngr gc [OPTIONS]
```

**Options:**

### What to Clean - Agent Resources

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--all-agent-resources` | boolean | Clean all agent resource types (machines, snapshots, volumes, work dirs) | `False` |
| `--machines` | boolean | Remove unused containers, instances, and sandboxes | `False` |
| `--snapshots` | boolean | Remove unused snapshots | `False` |
| `--volumes` | boolean | Remove unused volumes | `False` |
| `--work-dirs` | boolean | Remove work directories (git worktrees/clones) not in use by any agent | `False` |

### What to Clean - Mngr Resources

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--logs` | boolean | Remove log files from destroyed agents/hosts | `False` |
| `--build-cache` | boolean | Remove build cache entries | `False` |

### Filtering

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--include` | text | Only clean resources matching CEL filter (repeatable) | None |
| `--exclude` | text | Exclude resources matching CEL filter (repeatable) | None |

### Scope

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--all-providers` | boolean | Clean resources across all providers | `False` |
| `--provider` | text | Clean resources for a specific provider (repeatable) | None |

### Safety

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--dry-run` | boolean | Show what would be cleaned without actually cleaning | `False` |
| `--on-error` | choice (`abort` &#x7C; `continue`) | What to do when errors occur: abort (stop immediately) or continue (keep going) | `abort` |
| `-w`, `--watch` | integer | Re-run garbage collection at the specified interval (seconds) | None |

### Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | choice (`human` &#x7C; `json` &#x7C; `jsonl`) | Output format for command results | `human` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

### Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## CEL Filter Examples

CEL filters let you control which resources are cleaned.

**For snapshots, use `recency_idx` to filter by age:**
- `recency_idx == 0` - the most recent snapshot
- `recency_idx < 5` - the 5 most recent snapshots
- To keep only the 5 most recent: `--exclude "recency_idx < 5"`

**Filter by resource properties:**
- `name.contains("test")` - resources with "test" in the name
- `provider_name == "docker"` - Docker resources only


## See Also

- [mngr destroy](../primary/destroy.md) - Destroy agents (includes automatic GC)
- [mngr list](../primary/list.md) - List agents to find unused resources

## Examples

**Preview what would be cleaned (dry run)**

```bash
$ mngr gc --work-dirs --dry-run
```

**Clean all agent resources**

```bash
$ mngr gc --all-agent-resources
```

**Clean machines and snapshots for Docker**

```bash
$ mngr gc --machines --snapshots --provider docker
```

**Clean logs and build cache**

```bash
$ mngr gc --logs --build-cache
```

**Keep only the 5 most recent snapshots**

```bash
$ mngr gc --snapshots --exclude "recency_idx < 5"
```
