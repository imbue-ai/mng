# Changelings: Technical Architecture

## Relationship to mngr

Changelings is a thin orchestration layer on top of mngr:

- **mngr** handles: agent creation, process management, git operations, host lifecycle, idle detection
- **changelings** handles: scheduling, deployment to Modal, template management, config management

Changelings does NOT duplicate any mngr functionality. It simply calls `mngr create` with the right arguments.

## File layout

```
apps/changelings/
  pyproject.toml
  README.md
  docs/
    design.md                    # User-facing design document
  specs/
    architecture.md              # This file
  imbue/                         # Implicit namespace package (no __init__.py)
    changelings/
      __init__.py
      main.py                    # Click CLI group, entry point
      errors.py                  # Exception hierarchy
      primitives.py              # Domain-specific types
      data_types.py              # Frozen models (ChangelingDefinition, etc.)
      config.py                  # Config read/write (TOML persistence)
      templates.py               # Built-in template definitions and messages
      cli/
        __init__.py
        add.py                   # changeling add
        remove.py                # changeling remove
        list.py                  # changeling list
        update.py                # changeling update
        run.py                   # changeling run
        status.py                # changeling status
      deploy/                    # Modal deployment logic [future]
```

## Sequencing / implementation plan

### Phase 1: Foundation (complete)

- Project structure, CLI skeleton, data types, README, specs

### Phase 2: Config management (complete)

- Config read/write (`config.py`) with TOML persistence
- `changeling add` registers changelings to config
- `changeling list` displays registered changelings

### Phase 3: Local execution (complete)

- `changeling run --local` runs mngr create locally via subprocess
- Built-in template messages for all 9 changeling types (`templates.py`)
- End-to-end local testing of the agent flow without Modal

### Phase 4: Modal execution

- Implement `changeling run` without `--local` (runs on Modal)

### Phase 5: Modal deployment

- Implement `changeling add` to also create the scheduled Modal Function for a given changeling definition (see how we deploy a modal function in `mngr` for reference)

### Phase 6: Management commands

- Implement `changeling status` (basically just calls `mngr list` for the configured profile and filters down to those agents that were created by `changelings`)

### Phase 7: Polish

- Implement `changeling remove` (removes from config and undeploys the Modal App)
- Implement `changeling update` (modify an existing changeling's config and redeploy)
