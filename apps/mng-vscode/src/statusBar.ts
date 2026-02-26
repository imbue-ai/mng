import * as vscode from 'vscode';
import type { AgentSummary } from './types.js';

export class StatusBarManager {
    private readonly item: vscode.StatusBarItem;

    constructor() {
        this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
        this.item.command = 'workbench.view.extension.mng-agents';
        this.item.text = '$(vm) mng';
        this.item.tooltip = 'mng agent viewer';
    }

    register(context: vscode.ExtensionContext): void {
        context.subscriptions.push(this.item);
        this.item.show();
    }

    update(summary: AgentSummary): void {
        if (summary.totalAgents === 0) {
            this.item.text = '$(vm) mng: no agents';
            return;
        }
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
        this.item.text = `$(vm) mng: ${parts.join(' | ')}`;
    }
}
