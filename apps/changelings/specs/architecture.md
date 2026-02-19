# Changelings: Technical Architecture

## Relationship to mng

Changelings is a thin orchestration layer on top of mng:

- **mng** handles: agent creation, process management, git operations, host lifecycle, idle detection
- **changelings** handles: scheduling, deployment to Modal, agent type configuration, config management

Changelings does NOT duplicate any mng functionality. It simply calls `mng create` with the right arguments.

## File layout

```
apps/changelings/
  pyproject.toml
  README.md
  conftest.py                      # App-level pytest configuration
  docs/
    design.md                      # User-facing design document
  specs/
    architecture.md                # This file
  imbue/                           # Implicit namespace package (no __init__.py)
    changelings/
      __init__.py
      main.py                      # Click CLI group, entry point
      errors.py                    # Exception hierarchy
      primitives.py                # Domain-specific types
      data_types.py                # Frozen models (ChangelingDefinition, etc.)
      config.py                    # Config read/write (TOML persistence)
      mng_commands.py             # Shared helpers for building mng create commands
      conftest.py                  # Shared test fixtures
      cli/
        __init__.py
        options.py                 # Shared Click options decorator
        add.py                     # changeling add
        remove.py                  # changeling remove [stub]
        list.py                    # changeling list [stub]
        update.py                  # changeling update [stub]
        run.py                     # changeling run
        status.py                  # changeling status [stub]
      deploy/                      # Modal deployment logic
        __init__.py
        deploy.py                  # Pure helpers + deploy_changeling orchestration
        verification.py            # Deployment verification (modal run, poll, cleanup)
        cron_runner.py             # Modal app for cron-scheduled execution
```

## Sequencing / implementation plan

### Phase 1: Foundation (done)

- Project structure, CLI skeleton, data types, README, specs
- All commands raise `NotImplementedError`

### Phase 2: Config management (done)

- Implement config read/write (`config.py`)

### Phase 3: Local execution (done)

- Implement `changeling run` (runs mng create locally)
- Allow end-to-end testing of the agent flow without Modal

### Phase 4: Modal execution (done)

- Implement `changeling run` where we run on Modal

### Phase 5: Modal deployment (done)

- Implement `changeling add` to create the scheduled Modal Function
- Deploy verification: invoke function, poll for agent, destroy/stop

### Phase 6: Management commands

- Implement `changeling list`
- Implement `changeling status` (basically just calls `mng list` for the configured profile and filters down to those agents that were created by `changelings`)

### Phase 7: Polish

- Implement `changeling remove` (just removes the Modal App), `changeling update` (just an alias for `changeling add --update`)
