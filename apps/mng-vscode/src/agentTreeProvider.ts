import * as vscode from 'vscode';
import { AgentNode } from './agentNode.js';
import type { MngService } from './mngService.js';
import type { PrService } from './prService.js';
import type { AgentSummary, MngAgent, PrInfo } from './types.js';

const STATE_ORDER: Record<string, number> = {
    running: 0,
    waiting: 1,
    stopped: 2,
    done: 3,
    replaced: 4,
};

export class AgentTreeProvider implements vscode.TreeDataProvider<AgentNode> {
    private _onDidChangeTreeData = new vscode.EventEmitter<AgentNode | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private agents: MngAgent[] = [];
    private prs = new Map<string, PrInfo>();

    constructor(
        private readonly mngService: MngService,
        private readonly prService: PrService,
    ) {}

    async refresh(): Promise<void> {
        this.agents = await this.mngService.listAgents();

        const branches = this.agents
            .map(a => a.branch)
            .filter((b): b is string => b !== null);

        if (branches.length > 0) {
            this.prs = await this.prService.getPrsForBranches(branches);
        } else {
            this.prs.clear();
        }

        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: AgentNode): vscode.TreeItem {
        return element;
    }

    getChildren(element?: AgentNode): AgentNode[] {
        if (element) return [];

        return this.agents
            .slice()
            .sort((a, b) => {
                const aOrder = STATE_ORDER[a.state] ?? 5;
                const bOrder = STATE_ORDER[b.state] ?? 5;
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
}
