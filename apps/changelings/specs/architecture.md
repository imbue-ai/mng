# Changelings: Technical Architecture

## System overview

```
User
  |
  v
changeling CLI (add/remove/list/deploy/run/status)
  |
  v
Config file (~/.changelings/config.toml)
  |
  v (deploy)
Modal API
  |
  v
Modal App (one per changeling)
  |
  v (cron trigger)
Modal Function
  |
  v
git clone <target-repo>
  |
  v
mngr create --in local --no-connect --await-agent-stopped ...
  |
  v
Claude agent runs inside the Modal sandbox
  |
  v
Agent creates commits, pushes branch, opens PR via GitHub API
  |
  v
Function exits, sandbox torn down
```

## Component breakdown

### 1. CLI layer (`imbue/changelings/cli/`)

- Standard click commands following mngr conventions
- Each command reads/writes the config file and/or interacts with Modal
- Commands: `add`, `remove`, `list`, `deploy`, `run`, `status`

### 2. Config layer (`imbue/changelings/data_types.py`)

- `ChangelingDefinition`: frozen model representing one changeling
- `ChangelingConfig`: frozen model containing all changelings
- Config is persisted as TOML at `~/.changelings/config.toml`
- Config read/write functions in a separate `config.py` module

### 3. Template layer (`imbue/changelings/templates/`)

- Each template is a frozen model containing:
  - `name`: template identifier
  - `description`: human-readable description
  - `default_message`: the prompt sent to the agent
  - `default_mngr_args`: extra arguments for `mngr create`
  - `default_permissions`: permissions to grant (e.g., `github`)
- Templates are registered at import time in a registry
- Users can override any template default in their changeling config

### 4. Deployment layer (`imbue/changelings/deploy/`)

- Generates Modal App code for each changeling
- Each Modal App has:
  - A base image containing the full monorepo codebase
  - Modal secrets for GITHUB_TOKEN, ANTHROPIC_API_KEY, SSH keys
  - A single function with `@modal.Cron(schedule)` decorator
- The function body:
  1. Clones target repo
  2. Configures git identity and auth
  3. Calls `mngr create` via subprocess
  4. Captures and logs the result

### 5. Execution layer (runs inside Modal)

- The actual agent execution is delegated entirely to `mngr`
- `mngr create --in local` runs the agent process locally within the Modal sandbox
- The agent type (e.g., `claude`) handles all the actual work
- The template's message provides the agent's instructions

## Key design decisions

### One Modal App per changeling (not one function per changeling in a shared app)

- **Rationale**: Modal Apps are the unit of deployment and scheduling. Separate apps give independent lifecycle management, failure isolation, and clearer resource attribution
- **Trade-off**: More apps to manage, but each is very simple (single function)

### Using `mngr create --in local` inside Modal (not `--in modal`)

- **Rationale**: The Modal function sandbox IS the isolated environment. Creating a nested Modal sandbox would add unnecessary latency, complexity, and cost
- **Trade-off**: The agent runs with whatever resources the Modal function sandbox has. If the agent needs GPUs or large memory, the Modal App's resource config must reflect that

### Config in `~/.changelings/config.toml` (not per-repo)

- **Rationale**: Changelings are a user's personal set of scheduled agents. A single config file makes it easy to manage all changelings across all repos
- **Trade-off**: Can't share changeling configs via version control. Could add per-repo `.changelings.toml` later as an additional source

### Templates as code (not as config)

- **Rationale**: Templates contain complex prompts and logic. Keeping them as Python code allows them to reference constants, format strings dynamically, and be tested
- **Trade-off**: Adding a new template requires code changes (but this is intentional -- templates should be thoughtfully designed)

## Relationship to mngr

Changelings is a thin orchestration layer on top of mngr:

- **mngr** handles: agent creation, process management, git operations, host lifecycle, idle detection
- **changelings** handles: scheduling, deployment to Modal, template management, config management

Changelings does NOT duplicate any mngr functionality. It simply calls `mngr create` with the right arguments.

### Agent types vs templates

- **mngr agent types** (e.g., `claude`, `codex`) define HOW an agent runs (what process, what environment)
- **changeling templates** (e.g., `fixme-fairy`, `test-troll`) define WHAT an agent does (what prompt, what permissions, what branch naming)

A changeling template always uses an underlying mngr agent type (defaulting to `claude`).

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
        deploy.py                # changeling deploy
        run.py                   # changeling run
        status.py                # changeling status
      templates/                 # Built-in templates [future]
        __init__.py
        registry.py              # Template registry
        fixme_fairy.py
        test_troll.py
        coverage_hunter.py
        doc_reporter.py
        docstring_reporter.py
        security_reporter.py
        issue_fixer.py
        code_custodian.py
      deploy/                    # Modal deployment logic [future]
        __init__.py
        modal_app.py             # Modal App generation
        image.py                 # Base image building
```

## Sequencing / implementation plan

### Phase 1: Foundation (current)

- Project structure, CLI skeleton, data types, README, specs
- All commands raise `NotImplementedError`

### Phase 2: Config management

- Implement config read/write (`config.py`)
- Implement `changeling add`, `changeling remove`, `changeling list`
- Templates with default prompts

### Phase 3: Local execution

- Implement `changeling run --local` (runs mngr create locally)
- End-to-end testing of the agent flow without Modal

### Phase 4: Modal deployment

- Implement `changeling deploy` (generates and deploys Modal Apps)
- Implement `changeling status` (queries Modal for run history)
- Implement `changeling run` (triggers Modal function manually)

### Phase 5: Polish

- Result tracking and reporting
- Notifications (Slack, email)
- Per-repo config support
- Multi-repo support
