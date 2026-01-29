# ClaudeWebView

A standalone web viewer for Claude Code session transcripts.

## Design

- Backend: Python FastAPI server with Server-Sent Events (SSE) for live updates
- Frontend: React + TypeScript with Radix UI Themes (matching Sculptor's gold/sand theme)
- File watching: Automatically updates when the transcript file changes

## Setup

Build the frontend (one-time):

```bash
cd ClaudeWebView/frontend
npm install
npm run build
```

## Usage

### View by session ID

```bash
uv run claudewebview --session-id <session-uuid>
```

This searches `~/.claude/projects/*/` for a matching transcript file.

### View by file path

```bash
uv run claudewebview --transcript path/to/session.jsonl
```

### Options

| Option | Description |
|--------|-------------|
| `--session-id ID` | Claude Code session UUID to view |
| `--transcript PATH` | Path to transcript JSONL file |
| `--theme THEME` | UI theme: `light`, `dark`, or `system` (default: `system`) |
| `--port PORT` | Port to serve on (default: auto-select) |
| `--no-browser` | Don't open browser automatically |

### Examples

```bash
# View a session by ID
uv run claudewebview --session-id abc123def456

# View a specific file with dark theme
uv run claudewebview --transcript ~/.claude/projects/my-project/session.jsonl --theme dark

# Run on a specific port without opening browser
uv run claudewebview --transcript session.jsonl --port 8080 --no-browser
```

Note: The following features are planned but not yet documented:
- Frontend build output (`frontend-dist/`) requires running initial build per setup instructions
- Interactive chat input UI component exists but backend `/api/send` endpoint only logs to console (note: `docs/requirements.md` specifies no interactive features should be included)
