# Customization

`mngr` is designed to be highly customizable through configuration files, plugins, and custom agent types.

## Configuration Files

`mngr` loads configuration from multiple sources with the following precedence (lowest to highest):

1. User config: `~/.mngr/profiles/<profile_id>/settings.toml`
2. Project config: `.mngr/settings.toml` (at git root or context dir)
3. Local config: `.mngr/settings.local.toml` (at git root or context dir)
4. Environment variables: `MNGR_PREFIX`, `MNGR_HOST_DIR`, `MNGR_ROOT_NAME`
5. CLI arguments (highest precedence)

### Command Defaults

You can override default values for CLI command parameters in your config files. This is particularly useful for setting project-specific or user-specific defaults.

**How it works:**

- Config files can define default values for any CLI parameter using `[commands.<command_name>]` sections
- These defaults only apply when the user doesn't explicitly specify a value
- User-specified values (via CLI or environment) always take precedence

**Example:**

```toml
# .mngr/settings.toml

# Override defaults for the 'create' command
[commands.create]
new_host = "docker"           # Create in docker by default instead of local
connect = false               # Don't auto-connect after creation
ensure_clean = false          # Allow dirty working trees
name_style = "scifi"          # Use sci-fi style names by default
```

With this config:

- `mngr create` → Creates in docker, doesn't connect, allows dirty trees
- `mngr create --in local` → Creates locally (user override wins)
- `mngr create --connect` → Creates in docker but connects (user override wins)

**Parameter names:**

- Use the parameter name as it appears in the CLI (after click's conversion)
- Boolean flags: use `connect = true` or `connect = false` (not `--connect`/`--no-connect`)
- For flags with multiple forms like `--in`/`--new-host`, use the full form: `new_host = "docker"`

**Scope:**

Command defaults are particularly useful for:

- Project-specific workflows (e.g., always use docker for this project)
- Personal preferences (e.g., prefer fantasy names over english)
- Team conventions (e.g., standard provider or host settings)

**Note:** Some CLI arguments (like `--context`) affect which config file is loaded, so they are parsed before config defaults are applied. The implementation handles this correctly by loading the config first, then applying defaults only to parameters that weren't explicitly specified.

## See Also

- [Agent Types](./concepts/agent_types.md) - Creating custom agent types and overriding defaults
- [Plugins](./concepts/plugins.md) - Extending mngr with code
- [Provisioning](./concepts/provisioning.md) - Customizing agent setup
