import * as vscode from 'vscode';
import type { MngAgent, PrInfo } from './types.js';

export class AgentNode extends vscode.TreeItem {
    readonly agentId: string;
    readonly agent: MngAgent;
    readonly pr: PrInfo | null;

    constructor(agent: MngAgent, pr: PrInfo | null) {
        super(agent.name, vscode.TreeItemCollapsibleState.None);

        this.agentId = agent.id;
        this.agent = agent;
        this.pr = pr;

        // Description: PR info or branch or type
        if (pr) {
            this.description = `PR #${pr.number}: ${pr.title}`;
        } else if (agent.branch) {
            this.description = agent.branch;
        } else {
            this.description = agent.type;
        }

        // Tooltip
        const lines = [
            `**${agent.name}**`,
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

        // Icon
        this.iconPath = getAgentIcon(agent.state);

        // Context value for conditional menus
        const contexts: string[] = [agent.state];
        if (pr) contexts.push('hasPR');
        if (agent.url) contexts.push('hasUrl');
        if (agent.branch) contexts.push('hasBranch');
        this.contextValue = contexts.join(',');

        // Default click: open PR if available
        if (pr) {
            this.command = {
                command: 'mng.openPRSideBySide',
                title: 'Open PR',
                arguments: [this],
            };
        }
    }
}

function getAgentIcon(state: string): vscode.ThemeIcon {
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
