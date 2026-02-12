# changelings

Nightly autonomous agents that maintain your codebase while you sleep.

Each **changeling** is a scheduled agent that performs a specific maintenance task on your codebase: fixing FIXMEs, improving tests, fixing GitHub issues, etc.

Wake up to high-quality PRs that improve your code-base!

## How it works

```bash
# Create a changeling that fixes FIXMEs every night at 3am
changeling add fixme-fairy \
  --template fixme-fairy \
  --repo git@github.com:org/repo.git \
  --schedule "0 3 * * *"

# Test it locally
changeling run fixme-fairy --local

# See what's registered
changeling list

# See the help for more options
changeling --help
```

## Built-in templates

| Template | Description |
|----------|-------------|
| `fixme-fairy` | Finds all FIXMEs in the codebase and fixes them, one commit per fix, then creates a PR |
| `test-troll` | Improves tests: speeds them up, removes pointless ones, fixes flakes, increases coverage |
| `coverage-hunter` | Focused specifically on increasing test coverage without sacrificing speed |
| `doc-regent` | Produces a markdown report of doc/code inconsistencies |
| `code-guardian` | Creates a markdown report of the largest inconsistencies and problems in the codebase |
| `docstring-scribe` | Produces a markdown report of outdated docstrings |
| `security-soldier` | Produces a report of potential security issues and emails it to you (since it is sensitive) |
| `issue-servant` | Watches new GitHub issues and attempts to create PRs that fix them |
| `module-warden` | Reviews and improves a specific sub-module of the codebase |

## Commands

- `changeling add` -- Deploy a new changeling
- `changeling update` -- Modify a deployed changeling
- `changeling remove` -- Remove a changeling
- `changeling list` -- List all registered changelings
- `changeling run` -- Run a changeling immediately (for testing)
- `changeling status` -- Check deployment status and run history

## Architecture

See [docs/design.md](docs/design.md) for the full design document and [specs/architecture.md](specs/architecture.md) for the technical architecture.
