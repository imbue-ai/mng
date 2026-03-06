# Make .mng/settings.toml purely optional

## Problem

Currently, deploying a changeling requires a `.mng/settings.toml` file with an `[create_templates.entrypoint]` section that specifies the agent type. This is redundant -- the plugin should already have enough information to figure out what to run without it.

The `.mng/settings.toml` should be purely optional: a way for users to override defaults, not a requirement.

## Proposed behavior

When `mng create` is invoked for a changeling repo that has no `.mng/settings.toml`:

1. The plugin detects that this is a changeling repo (e.g., by the presence of a `thinking/PROMPT.md` file, a `GLOBAL.md` file, or a `changelings.toml` file)
2. Based on the repo structure, the plugin infers the correct agent type and configuration
3. The changeling is created and provisioned without requiring any `.mng/settings.toml`

When `.mng/settings.toml` *does* exist, it serves as explicit overrides on top of the inferred defaults.

## Detection heuristics

A directory is a changeling repo if it contains any of:
- `GLOBAL.md` at the root
- A `thinking/PROMPT.md` file
- A `changelings.toml` file

The specific agent type (e.g., `claude-changeling` vs `elena-code`) could be inferred from:
- An explicit `agent_type` field in `changelings.toml`
- The presence of role-specific markers
- Falling back to `claude-changeling` as the default

## Key decisions needed

- Where does the detection logic live? In the plugin's `override_command_options` hook? In a new hook?
- How does this interact with `changeling deploy`, which currently generates `.mng/settings.toml`? If settings are optional, the deploy command could skip this step entirely.
- Should the agent type be configurable in `changelings.toml` (which already exists and is the natural place for changeling-level config)?

## Scope

This affects:
- Plugin hooks (detection logic)
- `apps/changelings` deploy command (can simplify if settings are optional)
- `changelings.toml` schema (may need an `agent_type` field)
