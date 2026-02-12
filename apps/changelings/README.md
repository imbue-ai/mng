# changelings

Nightly autonomous agents that maintain your codebase while you sleep.

Each **changeling** is a scheduled agent that performs a specific maintenance task on your codebase -- fixing FIXMEs, improving tests, increasing coverage, writing reports, fixing GitHub issues, and more. Changelings are deployed as Modal Apps and run on a cron schedule, creating PRs for you to review in the morning.

## How it works

1. You register a changeling with a template, target repo, and schedule
2. You deploy it to Modal, where it becomes a cron-scheduled function
3. On each trigger, the Modal function runs `mngr create` to spin up an agent
4. The agent does its work (commits, PRs, reports) and shuts down
5. You review the results (PRs, issues, reports) at your convenience

## Quick start

```bash
# Register a changeling that fixes FIXMEs every night at 3am
changeling add nightly-fixmes \
  --template fixme-fairy \
  --repo git@github.com:myorg/myrepo.git \
  --schedule "0 3 * * *"

# Deploy it to Modal
changeling deploy nightly-fixmes

# Or test it immediately
changeling run nightly-fixmes

# See what's registered
changeling list

# Check run history
changeling status nightly-fixmes
```

## Built-in templates

| Template | Description |
|----------|-------------|
| `fixme-fairy` | Finds all FIXMEs in the codebase and fixes them, one commit per fix, then creates a PR |
| `test-troll` | Improves tests: speeds them up, removes pointless ones, fixes flakes, increases coverage |
| `coverage-hunter` | Focused specifically on increasing test coverage without sacrificing speed |
| `doc-reporter` | Produces a markdown report of doc/code inconsistencies |
| `docstring-reporter` | Produces a markdown report of outdated docstrings |
| `security-reporter` | Produces a markdown report of potential security issues |
| `issue-fixer` | Watches new GitHub issues and attempts to create PRs that fix them |
| `code-custodian` | Reviews and improves a specific sub-module of the codebase |

## Commands

- `changeling add` -- Register a new changeling
- `changeling remove` -- Remove a changeling
- `changeling list` -- List all registered changelings
- `changeling deploy` -- Deploy changeling(s) to Modal
- `changeling run` -- Run a changeling immediately (for testing)
- `changeling status` -- Check deployment status and run history

## Architecture

See [docs/design.md](docs/design.md) for the full design document and [specs/architecture.md](specs/architecture.md) for the technical architecture.
