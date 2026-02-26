# Agent-PR Viewer: Detailed Design Plan

## Problem Statement

When running multiple agents via `mng`, each agent typically works on its own branch and creates a PR. Currently there is no way to see all agents alongside their associated PRs in a unified view. The user has to manually track which agent produced which PR, then open each PR separately.

The goal: a UI that shows agents and their PRs side by side, so you can quickly see what each agent is doing and review its output.

---

## Decision: VS Code Extension

After evaluating the options (extending sculptor_web, building a standalone web app, or building a VS Code extension), a VS Code extension is the best choice for several reasons:

1. **VS Code is already open** while working with agents -- no extra browser tab needed.
2. **Side-by-side layout** is native to VS Code (editor columns, split panels).
3. **Terminal integration** lets you `mng connect` directly from the extension.
4. **Simple Browser** is built into VS Code and can render full GitHub PR pages (unlike iframes, which GitHub blocks via `X-Frame-Options: DENY`).
5. **The GitHub PR extension** already demonstrates this pattern working well.
6. **File diffs** are native to VS Code -- we can show agent changes without leaving the editor.

The extension will be a new package in the monorepo at `apps/mng-vscode/`.

---

## Architecture Overview

```
+--------------------------------------------------+
|  VS Code                                          |
|                                                   |
|  +------------+  +-----------------------------+  |
|  | Activity   |  | Editor Area                 |  |
|  | Bar Icon   |  |                             |  |
|  |            |  | +-------------------------+ |  |
|  | +--------+ |  | | Simple Browser:         | |  |
|  | | Agent  | |  | | github.com/org/repo/    | |  |
|  | | Tree   | |  | | pull/123                | |  |
|  | | View   | |  | |                         | |  |
|  | |        | |  | |                         | |  |
|  | | agent-a| |  | |                         | |  |
|  | |  RUNNING |  | |                         | |  |
|  | |  PR #12| |  | |                         | |  |
|  | |        | |  | |                         | |  |
|  | | agent-b| |  | +-------------------------+ |  |
|  | |  STOPPED |  |                             |  |
|  | |  PR #34| |  |                             |  |
|  | |        | |  |                             |  |
|  | +--------+ |  +-----------------------------+  |
|  +------------+                                   |
|  +----------------------------------------------+ |
|  | Status Bar: 2 agents running | 1 PR open     | |
|  +----------------------------------------------+ |
+--------------------------------------------------+
```

### Data Flow

```
mng CLI (Python)                    VS Code Extension (TypeScript)
=================                   ==============================

mng list --format json  <--------  child_process.execFile('uv', ['run', 'mng', 'list', ...])
  |                                  |
  v                                  v
JSON with agents + host info       Parse into AgentNode[] for TreeView
  |
  |  (new) includes branch name
  |
  v
gh pr list --json  <-----------   Enrich with PR data via `gh` CLI
  |                                  |
  v                                  v
PR number, URL, status             Merge into AgentNode with PR info
                                     |
                                     v
                                   TreeDataProvider fires onDidChangeTreeData
                                     |
                                     v
                                   TreeView renders agent list with PR status
```

---

## Part 1: Backend Changes (mng core)

### 1.1 Expose `created_branch_name` in AgentInfo

Currently, `created_branch_name` is stored in the agent's `data.json` on disk and accessible via `agent.get_created_branch_name()`, but it is **not** included in `AgentInfo` (the model used by `mng list`). This is the single most important backend change.

**File: `libs/mng/imbue/mng/interfaces/data_types.py`**

Add a new field to `AgentInfo`:

```python
class AgentInfo(FrozenModel):
    # ... existing fields ...

    branch: str | None = Field(default=None, description="Git branch created for this agent")
```

**File: `libs/mng/imbue/mng/api/list.py`**

In `_assemble_host_info()`, when building `AgentInfo` for online hosts (around line 517), add:

```python
agent_info = AgentInfo(
    # ... existing fields ...
    branch=agent.get_created_branch_name(),
)
```

And in the offline/fallback path (around line 544), add:

```python
agent_info = AgentInfo(
    # ... existing fields ...
    branch=agent_ref.created_branch_name,  # need to check if AgentReference has this
)
```

For the offline path, we need to verify that `AgentReference` carries the branch name. If not, it needs to be added there too (in `primitives.py` or wherever `AgentReference` is defined).

**File: `libs/mng/imbue/mng/cli/list.py`**

Add `"branch"` as an available field in the documentation section (the "Available Fields" help text). No code changes needed in the display logic since it already handles arbitrary fields via `_get_field_value`.

### 1.2 Consider: AgentReference changes

**File: `libs/mng/imbue/mng/primitives.py`** (or wherever `AgentReference` is defined)

If `AgentReference` does not already carry `created_branch_name`, add it:

```python
class AgentReference(FrozenModel):
    # ... existing fields ...
    created_branch_name: str | None = Field(default=None, description="Git branch created for this agent")
```

And populate it wherever `AgentReference` objects are constructed (in `host.py` `get_agent_references()`).

### 1.3 Update sculptor_web (optional, low priority)

The existing `sculptor_web` app at `apps/sculptor_web/` already does agent listing + iframe display. Once `AgentInfo` includes `branch`, sculptor_web's `AgentDisplayInfo` should be updated to include it too. This is a small follow-on change.

---

## Part 2: VS Code Extension Structure

### 2.1 Package Location and Tooling

```
apps/mng-vscode/
  package.json              # Extension manifest + dependencies
  tsconfig.json             # TypeScript configuration
  src/
    extension.ts            # Entry point: activate/deactivate
    agentTreeProvider.ts    # TreeDataProvider for the agent sidebar
    agentNode.ts            # TreeItem subclass for agents
    prService.ts            # Service to fetch PR info via `gh` CLI
    mngService.ts           # Service to call `mng list` and parse output
    commands.ts             # Command implementations (open PR, connect, refresh)
    statusBar.ts            # Status bar item management
    config.ts               # Extension configuration helpers
    types.ts                # Shared TypeScript types
  resources/
    icons/                  # Custom icons for agent states
      running.svg
      stopped.svg
      waiting.svg
      done.svg
  .vscodeignore             # Files to exclude from VSIX package
  README.md                 # Extension documentation
```

### 2.2 package.json (Extension Manifest)

Key sections of the manifest:

```jsonc
{
  "name": "mng-agent-viewer",
  "displayName": "MNG Agent Viewer",
  "description": "View mng agents and their pull requests side by side",
  "version": "0.1.0",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Other"],
  "activationEvents": [
    "workspaceContains:**/.mng"
  ],
  "main": "./out/extension.js",
  "contributes": {
    "viewsContainers": {
      "activitybar": [{
        "id": "mng-agents",
        "title": "MNG Agents",
        "icon": "resources/icons/mng.svg"
      }]
    },
    "views": {
      "mng-agents": [{
        "id": "mng.agentList",
        "name": "Agents",
        "icon": "resources/icons/mng.svg"
      }]
    },
    "viewsWelcome": [{
      "view": "mng.agentList",
      "contents": "No agents found.\n[Create Agent](command:mng.createAgent)\n[Refresh](command:mng.refresh)"
    }],
    "commands": [
      {
        "command": "mng.refresh",
        "title": "MNG: Refresh Agents",
        "icon": "$(refresh)"
      },
      {
        "command": "mng.openPR",
        "title": "MNG: Open Pull Request",
        "icon": "$(git-pull-request)"
      },
      {
        "command": "mng.openPRSideBySide",
        "title": "MNG: Open PR Side by Side",
        "icon": "$(split-horizontal)"
      },
      {
        "command": "mng.connectAgent",
        "title": "MNG: Connect to Agent",
        "icon": "$(terminal)"
      },
      {
        "command": "mng.openAgentUrl",
        "title": "MNG: Open Agent URL",
        "icon": "$(globe)"
      },
      {
        "command": "mng.stopAgent",
        "title": "MNG: Stop Agent",
        "icon": "$(debug-stop)"
      },
      {
        "command": "mng.pullFromAgent",
        "title": "MNG: Pull from Agent",
        "icon": "$(cloud-download)"
      },
      {
        "command": "mng.createAgent",
        "title": "MNG: Create Agent"
      }
    ],
    "menus": {
      "view/title": [{
        "command": "mng.refresh",
        "when": "view == mng.agentList",
        "group": "navigation"
      }],
      "view/item/context": [
        {
          "command": "mng.openPR",
          "when": "view == mng.agentList && viewItem =~ /hasPR/",
          "group": "inline@1"
        },
        {
          "command": "mng.connectAgent",
          "when": "view == mng.agentList && viewItem =~ /running/",
          "group": "inline@2"
        },
        {
          "command": "mng.openPRSideBySide",
          "when": "view == mng.agentList && viewItem =~ /hasPR/"
        },
        {
          "command": "mng.openAgentUrl",
          "when": "view == mng.agentList && viewItem =~ /hasUrl/"
        },
        {
          "command": "mng.stopAgent",
          "when": "view == mng.agentList && viewItem =~ /running/"
        },
        {
          "command": "mng.pullFromAgent",
          "when": "view == mng.agentList"
        }
      ]
    },
    "configuration": {
      "title": "MNG Agent Viewer",
      "properties": {
        "mng.pollInterval": {
          "type": "number",
          "default": 10,
          "description": "How often to refresh agent status (seconds)"
        },
        "mng.uvPath": {
          "type": "string",
          "default": "uv",
          "description": "Path to the uv binary"
        },
        "mng.ghPath": {
          "type": "string",
          "default": "gh",
          "description": "Path to the gh (GitHub CLI) binary"
        },
        "mng.repoRoot": {
          "type": "string",
          "default": "",
          "description": "Path to the repo root (auto-detected if empty)"
        },
        "mng.prOpenMode": {
          "type": "string",
          "enum": ["simpleBrowser", "external"],
          "default": "simpleBrowser",
          "description": "How to open PRs: in VS Code's Simple Browser or external browser"
        }
      }
    }
  }
}
```

### 2.3 Extension Entry Point (`extension.ts`)

```typescript
import * as vscode from 'vscode';
import { AgentTreeProvider } from './agentTreeProvider';
import { MngService } from './mngService';
import { PrService } from './prService';
import { registerCommands } from './commands';
import { StatusBarManager } from './statusBar';

let pollHandle: NodeJS.Timeout | undefined;

export function activate(context: vscode.ExtensionContext) {
    const mngService = new MngService();
    const prService = new PrService();
    const treeProvider = new AgentTreeProvider(mngService, prService);
    const statusBar = new StatusBarManager();

    // Register tree view
    const treeView = vscode.window.createTreeView('mng.agentList', {
        treeDataProvider: treeProvider,
        showCollapseAll: false,
    });
    context.subscriptions.push(treeView);

    // Register commands
    registerCommands(context, treeProvider, mngService);

    // Register status bar
    statusBar.register(context);

    // Start polling
    const config = vscode.workspace.getConfiguration('mng');
    const interval = config.get<number>('pollInterval', 10) * 1000;

    const poll = async () => {
        await treeProvider.refresh();
        statusBar.update(treeProvider.getAgentSummary());
    };

    poll(); // Initial fetch
    pollHandle = setInterval(poll, interval);
    context.subscriptions.push({ dispose: () => clearInterval(pollHandle) });

    // Re-read config on change
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('mng.pollInterval')) {
                if (pollHandle) clearInterval(pollHandle);
                const newInterval = config.get<number>('pollInterval', 10) * 1000;
                pollHandle = setInterval(poll, newInterval);
            }
        })
    );
}

export function deactivate() {
    if (pollHandle) clearInterval(pollHandle);
}
```

---

## Part 3: Core Services

### 3.1 MngService (`mngService.ts`)

Responsible for calling `mng list --format json` and parsing the output.

```typescript
import { execFile } from 'child_process';
import { promisify } from 'util';
import * as vscode from 'vscode';
import { MngAgent } from './types';

const execFileAsync = promisify(execFile);

export class MngService {

    async listAgents(): Promise<MngAgent[]> {
        const config = vscode.workspace.getConfiguration('mng');
        const uvPath = config.get<string>('uvPath', 'uv');
        const repoRoot = this.getRepoRoot();

        try {
            const { stdout } = await execFileAsync(
                uvPath,
                ['run', 'mng', 'list', '--format', 'json'],
                { cwd: repoRoot, timeout: 30000 }
            );

            const data = JSON.parse(stdout);
            return (data.agents || []).map((a: any) => this.parseAgent(a));
        } catch (err: any) {
            // If mng is not installed or not configured, return empty
            if (err.code === 'ENOENT') {
                vscode.window.showWarningMessage(
                    'mng CLI not found. Install it or configure mng.uvPath.'
                );
                return [];
            }
            throw err;
        }
    }

    async connectAgent(agentName: string): Promise<void> {
        const config = vscode.workspace.getConfiguration('mng');
        const uvPath = config.get<string>('uvPath', 'uv');

        const terminal = vscode.window.createTerminal({
            name: `mng: ${agentName}`,
            shellPath: '/bin/bash',
            shellArgs: ['-c', `${uvPath} run mng connect ${agentName}`],
        });
        terminal.show();
    }

    async stopAgent(agentName: string): Promise<void> {
        const config = vscode.workspace.getConfiguration('mng');
        const uvPath = config.get<string>('uvPath', 'uv');
        const repoRoot = this.getRepoRoot();

        await execFileAsync(uvPath, ['run', 'mng', 'stop', agentName], {
            cwd: repoRoot,
            timeout: 30000,
        });
    }

    async pullFromAgent(agentName: string): Promise<void> {
        const config = vscode.workspace.getConfiguration('mng');
        const uvPath = config.get<string>('uvPath', 'uv');
        const repoRoot = this.getRepoRoot();

        const terminal = vscode.window.createTerminal({
            name: `mng pull: ${agentName}`,
            shellPath: '/bin/bash',
            shellArgs: ['-c', `${uvPath} run mng pull ${agentName}`],
        });
        terminal.show();
    }

    private parseAgent(data: any): MngAgent {
        return {
            id: data.id,
            name: data.name,
            type: data.type,
            state: (data.state || '').toLowerCase(),
            branch: data.branch || null,
            url: data.url || null,
            createTime: data.create_time,
            runtimeSeconds: data.runtime_seconds,
            host: {
                id: data.host?.id,
                name: data.host?.name,
                providerName: data.host?.provider_name,
                state: data.host?.state,
            },
            labels: data.labels || {},
        };
    }

    private getRepoRoot(): string {
        const config = vscode.workspace.getConfiguration('mng');
        const configured = config.get<string>('repoRoot', '');
        if (configured) return configured;

        // Fall back to first workspace folder
        const folders = vscode.workspace.workspaceFolders;
        return folders?.[0]?.uri.fsPath || process.cwd();
    }
}
```

### 3.2 PrService (`prService.ts`)

Responsible for mapping branches to PRs using the `gh` CLI.

```typescript
import { execFile } from 'child_process';
import { promisify } from 'util';
import * as vscode from 'vscode';
import { PrInfo } from './types';

const execFileAsync = promisify(execFile);

export class PrService {
    // Cache: branch name -> PR info (with TTL)
    private cache = new Map<string, { pr: PrInfo | null; fetchedAt: number }>();
    private readonly CACHE_TTL_MS = 60_000; // 1 minute

    async getPrForBranch(branch: string): Promise<PrInfo | null> {
        // Check cache
        const cached = this.cache.get(branch);
        if (cached && Date.now() - cached.fetchedAt < this.CACHE_TTL_MS) {
            return cached.pr;
        }

        try {
            const pr = await this.fetchPr(branch);
            this.cache.set(branch, { pr, fetchedAt: Date.now() });
            return pr;
        } catch {
            this.cache.set(branch, { pr: null, fetchedAt: Date.now() });
            return null;
        }
    }

    /**
     * Bulk-fetch PRs for multiple branches efficiently.
     * Uses a single `gh pr list` call to get all open PRs, then matches by branch.
     */
    async getPrsForBranches(branches: string[]): Promise<Map<string, PrInfo>> {
        const result = new Map<string, PrInfo>();
        const uncached: string[] = [];

        // Check cache first
        for (const branch of branches) {
            const cached = this.cache.get(branch);
            if (cached && Date.now() - cached.fetchedAt < this.CACHE_TTL_MS) {
                if (cached.pr) result.set(branch, cached.pr);
            } else {
                uncached.push(branch);
            }
        }

        if (uncached.length === 0) return result;

        // Fetch all open PRs in one call
        try {
            const config = vscode.workspace.getConfiguration('mng');
            const ghPath = config.get<string>('ghPath', 'gh');

            const { stdout } = await execFileAsync(ghPath, [
                'pr', 'list',
                '--state', 'all',
                '--limit', '100',
                '--json', 'number,title,state,url,headRefName,isDraft,additions,deletions,reviewDecision',
            ], { timeout: 15000 });

            const prs: any[] = JSON.parse(stdout);
            const prByBranch = new Map<string, any>();
            for (const pr of prs) {
                prByBranch.set(pr.headRefName, pr);
            }

            for (const branch of uncached) {
                const pr = prByBranch.get(branch);
                if (pr) {
                    const prInfo: PrInfo = {
                        number: pr.number,
                        title: pr.title,
                        state: pr.state.toLowerCase(),
                        url: pr.url,
                        branch: pr.headRefName,
                        isDraft: pr.isDraft,
                        additions: pr.additions,
                        deletions: pr.deletions,
                        reviewDecision: pr.reviewDecision,
                    };
                    result.set(branch, prInfo);
                    this.cache.set(branch, { pr: prInfo, fetchedAt: Date.now() });
                } else {
                    this.cache.set(branch, { pr: null, fetchedAt: Date.now() });
                }
            }
        } catch {
            // gh not installed or not in a git repo -- silently return what we have
        }

        return result;
    }

    private async fetchPr(branch: string): Promise<PrInfo | null> {
        const config = vscode.workspace.getConfiguration('mng');
        const ghPath = config.get<string>('ghPath', 'gh');

        const { stdout } = await execFileAsync(ghPath, [
            'pr', 'view', branch,
            '--json', 'number,title,state,url,headRefName,isDraft,additions,deletions,reviewDecision',
        ], { timeout: 10000 });

        const pr = JSON.parse(stdout);
        return {
            number: pr.number,
            title: pr.title,
            state: pr.state.toLowerCase(),
            url: pr.url,
            branch: pr.headRefName,
            isDraft: pr.isDraft,
            additions: pr.additions,
            deletions: pr.deletions,
            reviewDecision: pr.reviewDecision,
        };
    }

    clearCache(): void {
        this.cache.clear();
    }
}
```

### 3.3 Types (`types.ts`)

```typescript
export interface MngAgent {
    id: string;
    name: string;
    type: string;
    state: string;            // "running", "stopped", "waiting", "replaced", "done"
    branch: string | null;    // created_branch_name (new field from Part 1)
    url: string | null;       // agent URL (e.g., ttyd web terminal)
    createTime: string;
    runtimeSeconds: number | null;
    host: {
        id: string;
        name: string;
        providerName: string;
        state: string;
    };
    labels: Record<string, string>;
}

export interface PrInfo {
    number: number;
    title: string;
    state: string;            // "open", "closed", "merged"
    url: string;
    branch: string;
    isDraft: boolean;
    additions: number;
    deletions: number;
    reviewDecision: string | null;  // "APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED", null
}

export interface AgentSummary {
    totalAgents: number;
    runningAgents: number;
    openPRs: number;
}
```

---

## Part 4: TreeView Implementation

### 4.1 AgentTreeProvider (`agentTreeProvider.ts`)

```typescript
import * as vscode from 'vscode';
import { MngService } from './mngService';
import { PrService } from './prService';
import { MngAgent, PrInfo, AgentSummary } from './types';
import { AgentNode } from './agentNode';

export class AgentTreeProvider implements vscode.TreeDataProvider<AgentNode> {
    private _onDidChangeTreeData = new vscode.EventEmitter<AgentNode | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private agents: MngAgent[] = [];
    private prs = new Map<string, PrInfo>();

    constructor(
        private mngService: MngService,
        private prService: PrService,
    ) {}

    async refresh(): Promise<void> {
        // Fetch agents
        this.agents = await this.mngService.listAgents();

        // Fetch PRs for all agents that have branches
        const branches = this.agents
            .map(a => a.branch)
            .filter((b): b is string => b !== null);

        if (branches.length > 0) {
            this.prs = await this.prService.getPrsForBranches(branches);
        }

        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: AgentNode): vscode.TreeItem {
        return element;
    }

    getChildren(element?: AgentNode): AgentNode[] {
        if (element) {
            // No children for agent nodes (flat list)
            return [];
        }

        // Root level: return all agents sorted by state (running first), then name
        return this.agents
            .sort((a, b) => {
                const stateOrder = { running: 0, waiting: 1, stopped: 2, done: 3, replaced: 4 };
                const aOrder = stateOrder[a.state as keyof typeof stateOrder] ?? 5;
                const bOrder = stateOrder[b.state as keyof typeof stateOrder] ?? 5;
                if (aOrder !== bOrder) return aOrder - bOrder;
                return a.name.localeCompare(b.name);
            })
            .map(agent => {
                const pr = agent.branch ? this.prs.get(agent.branch) ?? null : null;
                return new AgentNode(agent, pr);
            });
    }

    getAgentSummary(): AgentSummary {
        return {
            totalAgents: this.agents.length,
            runningAgents: this.agents.filter(a => a.state === 'running').length,
            openPRs: [...this.prs.values()].filter(pr => pr.state === 'open').length,
        };
    }

    getAgentByNode(node: AgentNode): MngAgent | undefined {
        return this.agents.find(a => a.id === node.agentId);
    }
}
```

### 4.2 AgentNode (`agentNode.ts`)

```typescript
import * as vscode from 'vscode';
import * as path from 'path';
import { MngAgent, PrInfo } from './types';

export class AgentNode extends vscode.TreeItem {
    readonly agentId: string;
    readonly agent: MngAgent;
    readonly pr: PrInfo | null;

    constructor(agent: MngAgent, pr: PrInfo | null) {
        // Label is agent name
        super(agent.name, vscode.TreeItemCollapsibleState.None);

        this.agentId = agent.id;
        this.agent = agent;
        this.pr = pr;

        // Description: shows PR info or branch
        if (pr) {
            this.description = `PR #${pr.number}: ${pr.title}`;
        } else if (agent.branch) {
            this.description = agent.branch;
        } else {
            this.description = agent.type;
        }

        // Tooltip: detailed info
        const lines = [
            `Agent: ${agent.name}`,
            `State: ${agent.state.toUpperCase()}`,
            `Type: ${agent.type}`,
            `Host: ${agent.host.name} (${agent.host.providerName})`,
        ];
        if (agent.branch) lines.push(`Branch: ${agent.branch}`);
        if (pr) {
            lines.push(`PR #${pr.number}: ${pr.title}`);
            lines.push(`PR Status: ${pr.state}${pr.isDraft ? ' (draft)' : ''}`);
            lines.push(`Changes: +${pr.additions} -${pr.deletions}`);
            if (pr.reviewDecision) lines.push(`Review: ${pr.reviewDecision}`);
        }
        if (agent.runtimeSeconds) {
            const mins = Math.floor(agent.runtimeSeconds / 60);
            lines.push(`Runtime: ${mins}m`);
        }
        this.tooltip = new vscode.MarkdownString(lines.join('  \n'));

        // Icon: based on agent state
        this.iconPath = this.getIcon(agent.state);

        // Context value: used for conditional menu items
        const contexts: string[] = [agent.state];
        if (pr) contexts.push('hasPR');
        if (agent.url) contexts.push('hasUrl');
        if (agent.branch) contexts.push('hasBranch');
        this.contextValue = contexts.join(',');

        // Default click action: open PR if available, otherwise show agent details
        if (pr) {
            this.command = {
                command: 'mng.openPRSideBySide',
                title: 'Open PR',
                arguments: [this],
            };
        }
    }

    private getIcon(state: string): vscode.ThemeIcon {
        switch (state) {
            case 'running':
                return new vscode.ThemeIcon('vm-running', new vscode.ThemeColor('testing.runAction'));
            case 'stopped':
                return new vscode.ThemeIcon('debug-stop', new vscode.ThemeColor('testing.iconFailed'));
            case 'waiting':
                return new vscode.ThemeIcon('watch', new vscode.ThemeColor('testing.iconQueued'));
            case 'done':
                return new vscode.ThemeIcon('check', new vscode.ThemeColor('testing.iconPassed'));
            case 'replaced':
                return new vscode.ThemeIcon('replace', new vscode.ThemeColor('descriptionForeground'));
            default:
                return new vscode.ThemeIcon('question');
        }
    }
}
```

---

## Part 5: Commands

### 5.1 Command Registration (`commands.ts`)

```typescript
import * as vscode from 'vscode';
import { AgentTreeProvider } from './agentTreeProvider';
import { AgentNode } from './agentNode';
import { MngService } from './mngService';

export function registerCommands(
    context: vscode.ExtensionContext,
    treeProvider: AgentTreeProvider,
    mngService: MngService,
): void {
    // Refresh
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.refresh', () => treeProvider.refresh())
    );

    // Open PR in Simple Browser (side by side)
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.openPRSideBySide', async (node: AgentNode) => {
            if (!node.pr) {
                vscode.window.showInformationMessage(`No PR found for agent ${node.agent.name}`);
                return;
            }

            const config = vscode.workspace.getConfiguration('mng');
            const mode = config.get<string>('prOpenMode', 'simpleBrowser');

            if (mode === 'simpleBrowser') {
                // Open in VS Code's built-in Simple Browser, in column 2 (side by side)
                await vscode.commands.executeCommand(
                    'simpleBrowser.show',
                    vscode.Uri.parse(node.pr.url),
                );
            } else {
                // Open in external browser
                await vscode.env.openExternal(vscode.Uri.parse(node.pr.url));
            }
        })
    );

    // Open PR (same as above but also available as context menu)
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.openPR', async (node: AgentNode) => {
            if (!node.pr) return;
            await vscode.env.openExternal(vscode.Uri.parse(node.pr.url));
        })
    );

    // Connect to agent (open terminal with mng connect)
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.connectAgent', async (node: AgentNode) => {
            await mngService.connectAgent(node.agent.name);
        })
    );

    // Open agent URL (e.g., ttyd web terminal)
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.openAgentUrl', async (node: AgentNode) => {
            if (!node.agent.url) return;
            await vscode.commands.executeCommand(
                'simpleBrowser.show',
                vscode.Uri.parse(node.agent.url),
            );
        })
    );

    // Stop agent
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.stopAgent', async (node: AgentNode) => {
            const confirm = await vscode.window.showWarningMessage(
                `Stop agent "${node.agent.name}"?`,
                { modal: true },
                'Stop'
            );
            if (confirm !== 'Stop') return;

            try {
                await mngService.stopAgent(node.agent.name);
                vscode.window.showInformationMessage(`Agent "${node.agent.name}" stopped.`);
                await treeProvider.refresh();
            } catch (err: any) {
                vscode.window.showErrorMessage(`Failed to stop agent: ${err.message}`);
            }
        })
    );

    // Pull from agent
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.pullFromAgent', async (node: AgentNode) => {
            await mngService.pullFromAgent(node.agent.name);
        })
    );

    // Create agent (opens terminal to run mng create interactively)
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.createAgent', () => {
            const terminal = vscode.window.createTerminal({ name: 'mng create' });
            terminal.sendText('uv run mng create');
            terminal.show();
        })
    );
}
```

### 5.2 Status Bar (`statusBar.ts`)

```typescript
import * as vscode from 'vscode';
import { AgentSummary } from './types';

export class StatusBarManager {
    private item: vscode.StatusBarItem;

    constructor() {
        this.item = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Left,
            50
        );
        this.item.command = 'workbench.view.extension.mng-agents';
        this.item.text = '$(vm) MNG';
        this.item.tooltip = 'MNG Agent Viewer';
    }

    register(context: vscode.ExtensionContext): void {
        context.subscriptions.push(this.item);
        this.item.show();
    }

    update(summary: AgentSummary): void {
        if (summary.totalAgents === 0) {
            this.item.text = '$(vm) MNG: no agents';
        } else {
            const parts: string[] = [];
            if (summary.runningAgents > 0) {
                parts.push(`${summary.runningAgents} running`);
            }
            if (summary.openPRs > 0) {
                parts.push(`${summary.openPRs} PRs`);
            }
            if (parts.length === 0) {
                parts.push(`${summary.totalAgents} agents`);
            }
            this.item.text = `$(vm) MNG: ${parts.join(' | ')}`;
        }
    }
}
```

---

## Part 6: Key Design Decisions and Trade-offs

### 6.1 How to Display PRs

**Decision: Use VS Code's Simple Browser.**

- GitHub blocks iframes (`X-Frame-Options: DENY`), so embedding in a Webview won't work.
- VS Code's Simple Browser (`simpleBrowser.show` command) opens a full browser tab within VS Code that can render GitHub pages, including authentication via the user's existing cookies.
- This gives a true side-by-side experience: agent list on the left sidebar, PR in the editor area.
- Alternative: render PR data ourselves via the GitHub API (like the GitHub PR extension does). This is much more work and provides a worse experience for the initial version. It could be a future enhancement.

### 6.2 How to Get Agent Data

**Decision: Shell out to `mng list --format json`.**

- Directly reuses all existing mng infrastructure (provider discovery, host connectivity, etc.).
- No need to duplicate Python logic in TypeScript.
- The JSON output already contains all needed fields (after the Part 1 change to add `branch`).
- Trade-off: each poll spawns a subprocess. At a 10-second interval this is negligible.
- Alternative considered: a long-running mng server with a REST API. Much more complex, not worth it for v1.

### 6.3 How to Get PR Data

**Decision: Shell out to `gh pr list --json`.**

- The `gh` CLI is widely installed and handles auth transparently.
- A single `gh pr list --limit 100` call gets all PRs, which we match by branch name.
- Results are cached for 60 seconds to avoid hammering the GitHub API.
- Alternative considered: using the VS Code GitHub authentication API + Octokit directly. This would be more integrated but adds complexity. Could be a v2 enhancement.

### 6.4 Polling vs. Watching

**Decision: Polling with configurable interval (default 10s).**

- `mng list` gathers data from potentially multiple providers (local, docker, modal), so there is no single filesystem path to watch.
- 10-second intervals provide near-real-time updates without excessive overhead.
- The user can adjust the interval via `mng.pollInterval` setting.
- Future enhancement: watch `~/.mng/agents/` for filesystem changes to supplement polling.

### 6.5 Flat List vs. Hierarchy

**Decision: Flat list of agents, sorted by state then name.**

- Most users have a manageable number of agents (5-20).
- A flat list with state-based sorting (running agents first) is faster to scan.
- The description field shows PR info, so the user sees the connection immediately.
- Future enhancement: group by host, by project label, or by PR status.

---

## Part 7: Implementation Phases

### Phase 1: Backend (Part 1) -- ~2 hours

1. Add `branch` field to `AgentInfo` in `data_types.py`
2. Populate `branch` from `agent.get_created_branch_name()` in `api/list.py`
3. Ensure `AgentReference` carries `created_branch_name` for offline agents
4. Update the "Available Fields" documentation in `cli/list.py`
5. Run all tests, verify JSON output includes `branch`
6. Manual verification: `uv run mng list --format json | python -m json.tool` and confirm branch appears

### Phase 2: Extension Scaffold -- ~3 hours

1. Create `apps/mng-vscode/` directory structure
2. Set up `package.json` with all contributions (views, commands, configuration)
3. Set up TypeScript build (`tsconfig.json`, npm scripts)
4. Implement `extension.ts` entry point
5. Implement `types.ts` with all interfaces
6. Implement `config.ts` for reading extension settings
7. Verify extension loads in VS Code (`F5` to debug)

### Phase 3: Data Layer -- ~3 hours

1. Implement `MngService` -- call `mng list`, parse JSON, return typed data
2. Implement `PrService` -- call `gh pr list`, parse JSON, cache results
3. Write unit tests for JSON parsing logic
4. Manual verification: run services standalone and check output

### Phase 4: TreeView -- ~3 hours

1. Implement `AgentTreeProvider` -- fetch data, provide tree items
2. Implement `AgentNode` -- labels, descriptions, icons, context values
3. Wire up to extension activation
4. Implement refresh command and polling
5. Manual verification: see agents appear in sidebar with correct state icons

### Phase 5: Commands and Interactions -- ~3 hours

1. Implement "Open PR" command (Simple Browser)
2. Implement "Connect to Agent" command (terminal integration)
3. Implement "Stop Agent" command (with confirmation)
4. Implement "Pull from Agent" command
5. Implement "Open Agent URL" command
6. Implement status bar
7. Wire up context menus (inline buttons and right-click)
8. Manual verification: test each command end-to-end

### Phase 6: Polish -- ~2 hours

1. Error handling for missing `mng`, `gh`, or `uv` binaries
2. Loading states (show "Refreshing..." in tree view)
3. Empty states (welcome view when no agents found)
4. Icon design for the Activity Bar
5. README with installation instructions
6. Handle edge cases: agent with no branch, branch with no PR, PR that was merged

---

## Part 8: Future Enhancements (Not in v1)

1. **Webview Dashboard**: A rich webview panel showing agent timelines, PR status, and resource usage charts. Would replace or supplement the tree view for power users.

2. **Inline PR Review**: Render PR diffs directly in VS Code using `registerTextDocumentContentProvider`, similar to the GitHub PR extension. Would allow code review without leaving VS Code.

3. **Agent Logs**: Stream agent logs into a VS Code Output Channel using `mng logs`.

4. **Create Agent UI**: A webview form for creating agents with all the `mng create` options, instead of dropping into a terminal.

5. **Auto-Open on Agent Completion**: Watch for agents transitioning from RUNNING to DONE and automatically open their PR.

6. **Group by Project/Host**: Allow users to group agents by project label, host, or provider.

7. **PR Status Badges**: Show CI status, review status, and merge-readiness as badges on tree items.

8. **Notifications**: VS Code notifications when an agent finishes, a PR is approved, or CI fails.

9. **Multi-Repo Support**: Track agents across multiple repositories.

10. **Authentication Integration**: Use VS Code's built-in GitHub authentication instead of relying on `gh` CLI.

---

## Part 9: Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Simple Browser may not render GitHub well | Users can't review PRs in VS Code | Fall back to `openExternal`; expose `mng.prOpenMode` config |
| `gh` CLI not installed | No PR info | Gracefully degrade: show branch name instead of PR info |
| `mng list` is slow (e.g., querying modal) | UI feels sluggish | Show cached data immediately, update in background; add loading indicator |
| Agent state changes between polls | Stale data shown briefly | 10s default interval is reasonable; manual refresh available |
| Too many agents overwhelm tree view | Hard to find specific agent | Search/filter support (future); sorting by state helps |
| `simpleBrowser.show` is an internal command | Could break in future VS Code versions | It has been stable for years; fall back to `openExternal` if it fails |

---

## Summary

The plan involves two main workstreams:

1. **Backend**: Add `branch` to `AgentInfo` so `mng list --format json` includes the git branch for each agent. This is a small, well-scoped change touching 2-3 files.

2. **VS Code Extension**: A new TypeScript package that reads from `mng list` and `gh pr list`, presents agents in a sidebar tree view, and opens PRs in VS Code's Simple Browser for side-by-side viewing.

The extension follows the same architectural pattern as the Docker extension (poll CLI for status, show in tree view, actions via context menus) and the GitHub PR extension (show PR data alongside code).

Total estimated effort: ~16 hours for a functional v1.
