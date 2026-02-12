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
      config.py                  # Config read/write (TOML persistence) [future]
      cli/
        __init__.py
        add.py                   # changeling add
        remove.py                # changeling remove
        list.py                  # changeling list
        update.py                # changeling update
        run.py                   # changeling run
        status.py                # changeling status
      deploy/                    # Modal deployment logic
```

## Sequencing / implementation plan

### Phase 1: Foundation (current)

- Project structure, CLI skeleton, data types, README, specs
- All commands raise `NotImplementedError`

### Phase 2: Config management

- Implement config read/write (`config.py`)

### Phase 3: Local execution

- Implement `changeling run` (runs mngr create locally)
- Allow end-to-end testing of the agent flow without Modal

### Phase 4: Modal execution

- Implement `changeling run` where we run on Modal

### Phase 4: Modal deployment

- Implement `changeling add` to create the scheduled Modal Function for a given changeling definition (see how we deploy a modal function in `mngr` for reference)

### Phase 4: Management commands
- 
- Implement `changeling list`
- Implement `changeling status` (basically just calls `mngr list` for the configured profile and filters down to those agents that were created by `changelings`)

### Phase 5: Polish

- Implement `changeling remove` (just removes the Modal App), `changeling update` (just an alias for `changeling add --update`)
