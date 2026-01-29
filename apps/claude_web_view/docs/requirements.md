# ClaudeWebView Requirements

## Overview

ClaudeWebView is a standalone application that provides a web-based viewer for Claude Code sessions. It recreates Sculptor's chat panel experience but operates independently, reading directly from Claude Code's transcript files.


## Behavior

The application should:
1. Launch as a command line application
2. Take a Claude Code session ID as a parameter
3. Find the transcript file for that session and parse it to extract user and agent messages and tool uses
4. Expose a local HTTP port that the user can connect to with their browser to view the parsed messages
5. Use the same look and feel as Sculptor's chat pane to render the messages
6. Watch for new updates to the transcript file and keep adding to the chat view


## Requirements

* CLI
   * Parameters:
      * Required: `--session-id <uuid>` or `--transcript <path>`
      * Optional: `--port` (default: auto-generate)
      * Optional: `--theme [light, dark, system]` (default: system). Inject this in the html so the UI knows how to render.
   * Set up a file system watcher on the transcript file
   * Support both completed and in-progress claude sessions
   * Handle an incomplete final record gracefully, e.g. if the write is in progress when we start parsing.
   * Fail immediately with a clear error on any other error condition: file doesn't exist, malformed file, etc.
* UI
   * Render all user and agent messages and tool calls
   * Render markdown and collapsible tools
   * None of the interactive features of Sculptor, e.g. no verifier, fork, prompt input, etc.
   * Support light and dark themes
* Code
   * This project must have zero dependencies on anything else in the repo
   * Do not use or create shared libraries
   * Implement new parsing, and copy any relevant styles, etc.


## Key Constraint

This folder must have **no dependencies on anything else in the repository**. The goal is to eventually move ClaudeWebView into its own separate repository.

---

## Technical Context

### Claude Code Transcript Format

Transcripts are stored as JSONL files at:
```
~/.claude/projects/{sanitized-project-path}/{session_id}.jsonl
```

Each line is a JSON object with a `type` field:
- `system` (subtype: `init`) - Session initialization with session_id, MCP servers, tools
- `assistant` - Agent responses with content blocks (text, tool_use)
- `user` - Tool results and user messages
- `result` - End of stream with status, duration, cost, token usage

### Content Block Types

Messages contain arrays of typed content blocks. Note, these are Sculptor-specific types. We need to verify which of these actually exist in claude transcript files:
- `TextBlock` - Markdown text content
- `ToolUseBlock` - Tool invocation with name and input parameters
- `ToolResultBlock` - Tool execution output
- `ErrorBlock` [future] - Error messages with traceback
- `WarningBlock` [future] - Warning messages
- `ContextSummaryBlock` [future] - Compaction summaries
- `FileBlock` [future] - Attached files/images

### Sculptor Chat UI Reference

Sculptor's chat panel (in `sculptor/frontend/src/pages/chat/`) uses:
- React + TypeScript with Radix UI components
- Jotai atoms for state management
- `Message.tsx` - Delegates to UserMessage/AssistantMessage based on role
- `MarkdownBlock` - Renders markdown content
- `CollapsibleToolSection` - Renders tool use/result pairs
- SCSS modules for styling

---

## Technology Stack

The goal is to reuse Sculptor's Radix UI components and SCSS styling with the minimal necessary dependencies.

### Frontend (Required for Radix + SCSS)

| Layer | Technology | Why |
|-------|-----------|-----|
| **UI Library** | React 18 | Radix UI is React-only |
| **Bundler** | Vite | Best SCSS module support, fast, simple config |
| **Design System** | @radix-ui/themes | Core styling + components (Box, Flex, Text, ScrollArea, etc.) |
| **Styling** | SCSS modules | Sculptor uses `*.module.scss` throughout |
| **Markdown** | react-markdown + remark-gfm + remark-emoji | Direct lift from Sculptor |
| **Syntax Highlighting** | highlight.js | Used by MarkdownBlock |

### Backend

| Layer | Technology | Why |
|-------|-----------|-----|
| **Server** | Python + FastAPI | Serve static files + SSE endpoint for live updates |
| **File Watching** | watchfiles (Python) | Efficient cross-platform file watching |

### Explicitly Not Using (vs. full Sculptor)

- Electron and all desktop-related deps
- Jotai (state is much simpler - just a list of messages)
- TipTap (no rich text input needed)
- react-router (single page, no routing)
- API client generation tooling
- Testing frameworks
- Sentry/analytics

### Frontend Dependencies

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "@radix-ui/themes": "^3.1.0",
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "remark-emoji": "^5.0.0",
    "highlight.js": "^11.9.0"
  },
  "devDependencies": {
    "vite": "^5.4.0",
    "@vitejs/plugin-react": "^4.0.0",
    "typescript": "^5.5.0",
    "sass": "^1.77.0"
  }
}
```

### Project Structure

```
ClaudeWebView/
├── cli/                    # Python CLI + FastAPI server
│   ├── __main__.py         # Entry point
│   ├── server.py           # FastAPI app (static files + SSE)
│   ├── parser.py           # JSONL transcript parser
│   └── watcher.py          # File watcher
├── frontend/               # React app (Vite)
│   ├── src/
│   │   ├── App.tsx         # Main component
│   │   ├── components/     # Message, MarkdownBlock, ToolBlock, etc.
│   │   └── styles/         # Copied/adapted SCSS from Sculptor
│   ├── package.json
│   └── vite.config.ts
├── docs/
│   └── requirements.md
└── pyproject.toml          # Python package config
```

### Runtime Flow

1. User runs `claudewebview --session-id <uuid>` or `claudewebview --latest` [future]
2. Python CLI locates the transcript file
3. FastAPI server starts, serving the pre-built React frontend
4. CLI prints URL
5. User opens browser to `http://localhost:<port>`
6. Frontend connects to SSE endpoint for live updates
7. File watcher detects changes to transcript, pushes new messages via SSE
8. React app renders messages using Radix components and Sculptor-style SCSS

---

Note: The following features are planned but not yet documented elsewhere:
- Session listing/discovery functionality
- Session cost and duration summary display (data is in transcript but not shown in UI)
- Frontend must be built (`npm run build` in frontend/) to create frontend-dist directory before the app can run