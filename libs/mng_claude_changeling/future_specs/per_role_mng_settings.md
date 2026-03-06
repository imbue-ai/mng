# Per-role .mng/settings.toml with symlink trick

## Problem

Currently there is a single `.mng/settings.toml` at the repo root that all role agents share. This makes it impossible for different roles to have different mng configurations (e.g., different idle timeouts, different create templates, different agent type defaults).

The plugin already uses a symlink trick for `.claude/` (symlinking to `<active_role>/.claude/`). The same pattern should apply to `.mng/settings.toml`.

## Proposed behavior

1. Each role directory gets its own `.mng/settings.toml`:
   - `thinking/.mng/settings.toml` - thinking role's mng configuration
   - `working/.mng/settings.toml` - working role's mng configuration
   - `verifying/.mng/settings.toml` - verifying role's mng configuration
2. The repo root `.mng/settings.toml` is a symlink to `<active_role>/.mng/settings.toml`
3. The current default `.mng/settings.toml` content (the entrypoint template) moves into the `thinking/` role directory, since the thinking role is the primary role agent that gets deployed first

## Migration

- Existing changelings with a root-level `.mng/settings.toml` should continue to work (the plugin should detect the non-symlink case and either migrate or leave it alone)
- New changelings created via `changeling deploy` should use the per-role structure from the start

## Key decisions needed

- Should provisioning create the symlink (like it does for `.claude/`), or should `changeling deploy` set this up?
- How does this interact with the "generate .mng/settings.toml" spec? If the plugin generates settings, it probably generates them per-role.

## Scope

This affects:
- `ClaudeChangelingAgent.provision()` in `plugin.py` (symlink creation)
- `provisioning.py` (default content generation)
- `apps/changelings` deploy command (initial repo structure)
