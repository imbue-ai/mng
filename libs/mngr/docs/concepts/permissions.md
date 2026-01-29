# Permissions

Agents have a list of "permissions" that control both what they are allowed to do and what information they have access to. [future] Permissions are stored but not enforced during agent operations.

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

Run [`limit --help`](../commands/secondary/limit.md) [future] for the full list of available permissions.

Note: The following features are planned but not yet documented: `on_validate_permissions` hook, `--grant` flag application during agent creation.