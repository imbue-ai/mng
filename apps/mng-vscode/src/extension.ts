import * as vscode from 'vscode';
import { AgentTreeProvider } from './agentTreeProvider.js';
import { registerCommands } from './commands.js';
import { getConfig } from './config.js';
import { MngService } from './mngService.js';
import { PrService } from './prService.js';
import { StatusBarManager } from './statusBar.js';

let pollHandle: ReturnType<typeof setInterval> | undefined;

export function activate(context: vscode.ExtensionContext): void {
    const mngService = new MngService();
    const prService = new PrService();
    const treeProvider = new AgentTreeProvider(mngService, prService);
    const statusBar = new StatusBarManager();

    const treeView = vscode.window.createTreeView('mng.agentList', {
        treeDataProvider: treeProvider,
        showCollapseAll: false,
    });
    context.subscriptions.push(treeView);

    registerCommands(context, treeProvider, mngService);
    statusBar.register(context);

    const poll = async () => {
        await treeProvider.refresh();
        statusBar.update(treeProvider.getAgentSummary());
    };

    // Initial fetch
    poll();

    // Start polling
    const config = getConfig();
    const intervalMs = config.pollInterval * 1000;
    pollHandle = setInterval(poll, intervalMs);
    context.subscriptions.push({ dispose: () => { if (pollHandle) clearInterval(pollHandle); } });

    // Re-configure polling on settings change
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('mng.pollInterval')) {
                if (pollHandle) clearInterval(pollHandle);
                const newInterval = getConfig().pollInterval * 1000;
                pollHandle = setInterval(poll, newInterval);
            }
        }),
    );
}

export function deactivate(): void {
    if (pollHandle) {
        clearInterval(pollHandle);
        pollHandle = undefined;
    }
}
