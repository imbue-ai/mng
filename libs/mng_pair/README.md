# mng-pair

A plugin for [mng](https://github.com/imbue-ai/mng) that adds the `mng pair` command for continuous bidirectional file sync between an agent and a local directory. **[experimental]**

## Overview

`mng pair` establishes a real-time file sync between an agent's working directory and a local directory using [unison](https://www.cis.upenn.edu/~bcpierce/unison/). If git repositories exist on both sides, the command first synchronizes git state (branches and commits) before starting the continuous file sync.

Press Ctrl+C to stop the sync.

## Requirements

- [unison](https://www.cis.upenn.edu/~bcpierce/unison/) must be installed
- On macOS, `unison-fsmonitor` is also required for file watching

## Usage

```bash
# Pair with an agent (syncs to nearest git root or current directory)
mng pair my-agent

# Pair to a specific local directory
mng pair my-agent --target ./local-dir

# One-way sync (source to target only)
mng pair my-agent --sync-direction=forward

# One-way sync (target to source only)
mng pair my-agent --sync-direction=reverse

# Prefer source side on conflicts
mng pair my-agent --conflict=source

# Prefer the newer file on conflicts (default)
mng pair my-agent --conflict=newer

# Filter to agents on a specific host
mng pair my-agent --source-host @local

# Include/exclude files by glob pattern
mng pair my-agent --include "*.py" --exclude "__pycache__"
```

## Options

### Source Selection
- `--source` -- Source specification: AGENT, AGENT:PATH, or PATH
- `--source-agent` -- Source agent name or ID
- `--source-host` -- Source host name or ID
- `--source-path` -- Path within the agent's work directory

### Target
- `--target` -- Local target directory (default: nearest git root or current directory)

### Git Handling
- `--require-git / --no-require-git` -- Require both sides to be git repos (default: required)
- `--uncommitted-changes` -- How to handle uncommitted changes: stash, clobber, merge, or fail (default: fail)

### Sync Behavior
- `--sync-direction` -- both (bidirectional), forward (source->target), reverse (target->source) (default: both)
- `--conflict` -- Conflict resolution: newer, source, target, or ask (default: newer)

### File Filtering
- `--include` -- Include files matching glob pattern (repeatable)
- `--exclude` -- Exclude files matching glob pattern (repeatable)

## Installation

`mng-pair` is installed as part of the mng monorepo:

```bash
uv sync --all-packages
```

The plugin registers itself automatically via setuptools entry points.
