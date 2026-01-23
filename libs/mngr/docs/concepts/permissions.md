# Permissions

Agents have a list of "permissions" that control both what they are allowed to do and what information they have access to.

This list is a simple list of strings. The valid strings are entirely defined by plugins.

Permissions end up looking something like this:

```
[
    "github:*",
    "anthropic:claude-code:write",
    "user_data:email",
    ...
]
```

The first part of the permission string is the plugin name (e.g., `github`, `anthropic`, `user_data`). Everything after that is defined by the plugin itself.

## Available Permissions

Run [`limit --help`](../commands/secondary/limit.md) for the full list of available permissions.

## TODOs

The following features are documented but not yet implemented:

- **`limit` command** - CLI command for listing available permissions and granting/revoking permissions
- **Permission enforcement** - Permissions are stored but never checked or validated during agent operations
- **`on_validate_permissions` hook** - Plugin hook for validating permissions is not called
- **Permission application** - Permissions granted via `--grant` flag or agent type configs are not actually applied to agents during creation
