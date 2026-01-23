Uses uv. Run tests like this:

    uv run pytest

Run the development version of the tool like this:

    uv run claude-code-transcripts --help

Always practice TDD: write a faliing test, watch it fail, then make it pass.

Commit early and often. Commits should bundle the test, implementation, and documentation changes together.

Run Black to format code before you commit:

    uv run black .

## TODOs - Agent Session Features Not Yet Implemented

- Agent-specific visual indicators in HTML output (no way to distinguish agent sessions from regular sessions in rendered transcripts)
- Agent metadata handling (no special processing for agent configuration or behavior markers)
- `--include-agents` flag for `local`, `json`, and `web` commands (currently only available on `all` command)
- Documentation explaining what agent sessions are and why they're excluded by default
- Agent-specific summary extraction or display formatting
