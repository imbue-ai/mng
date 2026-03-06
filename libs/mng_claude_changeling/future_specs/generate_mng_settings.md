# Generate .mng/settings.toml from role directories

## Problem

The changeling plugin's core job is transforming a directory of text files (role directories with prompts, skills, and configuration) into a valid set of mng agent configurations. Currently, users must manually create `.mng/settings.toml` with the correct agent type mappings. The plugin should be able to generate this file automatically.

## Proposed behavior

During provisioning, the plugin should:

1. Scan the changeling repo for role directories (any directory containing a `PROMPT.md` file)
2. For each discovered role, generate an appropriate `[create_templates.<role>]` entry in `.mng/settings.toml`
3. The thinking role maps to the `claude-changeling` agent type (or the specific subtype like `elena-code`)
4. Other roles (working, verifying, user-defined) map to their own agent types derived from the parent changeling type
5. The talking role is special (uses `llm live-chat`, not Claude Code) and gets its own configuration

## Key decisions needed

- Should the generated `.mng/settings.toml` be committed to git, or treated as a derived artifact (like `.claude/settings.local.json`)?
- How should user overrides work? If the user has manually edited `.mng/settings.toml`, the plugin should not clobber their changes.
- Should each role's agent type be a separate registered type, or should it be a custom type defined via `parent_type` in the TOML?

## Scope

This affects:
- `ClaudeChangelingAgent.provision()` in `plugin.py`
- Possibly `provisioning.py` (new function for generating settings)
- The deploy command in `apps/changelings` (which currently writes `.mng/settings.toml` with a hardcoded entrypoint template)
