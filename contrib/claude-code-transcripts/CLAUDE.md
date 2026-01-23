# claude-code-transcripts - Implementation Guide

This tool converts Claude Code session files (JSON or JSONL) to clean, mobile-friendly HTML pages with pagination.

## Implemented Features

### Commands (All 4 Implemented)
- `local` - Select from local sessions in `~/.claude/projects` (default command)
- `web` - Select from web sessions via Claude API
- `json` - Convert specific JSON/JSONL file (including URLs)
- `all` - Convert all local sessions to browseable archive

### Output Options (All 6 Implemented)
- `-o, --output DIRECTORY` - Specify output directory
- `-a, --output-auto` - Auto-name subdirectory based on session ID/filename
- `--repo OWNER/NAME` - GitHub repo for commit links (auto-detects from git push)
- `--open` - Open generated HTML in browser
- `--gist` - Upload to GitHub Gist with preview URL
- `--json` - Include original session file in output

### Local Sessions (Fully Implemented)
- `--limit N` - Control number of sessions shown (default: 10)
- Auto-discovery from `~/.claude/projects`
- Filters out agent files and empty sessions

### Web Sessions (Fully Implemented)
- Interactive session picker from API
- Direct session ID argument
- macOS keychain auth (auto-retrieval)
- Manual `--token` and `--org-uuid` fallback
- Config file support (`~/.claude.json`)

### GitHub Gist Publishing (Fully Implemented)
- Creates gist via `gh` CLI
- Outputs gist.github.com URL
- Generates gisthost.github.io preview URL
- JavaScript injection for proper rendering

### All Sessions Batch Conversion (Fully Implemented)
- `--include-agents` - Include agent session files
- `--dry-run` - Preview without creating files
- `--quiet` - Suppress non-error output
- `--open` - Open archive in browser
- Master index with per-project pages

### Core Functionality (Fully Implemented)
- JSONL parsing (local format)
- JSON parsing (web format)
- URL fetching for remote files
- Paginated HTML generation
- Mobile-friendly responsive design
- Tool statistics and formatting
- Git commit detection and linking
- Search functionality in HTML
- Session continuation handling
- Comprehensive test coverage

## TODO

All documented features are implemented. Future enhancements could include:

- Syntax highlighting themes/customization
- Export to additional formats (PDF, Markdown)
- Custom CSS/template support
- Incremental archive updates (skip already-converted sessions)
- Session comparison/diff view
- Full-text search across all sessions in archive
- Filtering sessions by date range or project
