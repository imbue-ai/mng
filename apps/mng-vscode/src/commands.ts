import * as vscode from 'vscode';
import type { AgentNode } from './agentNode.js';
import type { AgentTreeProvider } from './agentTreeProvider.js';
import { getConfig } from './config.js';
import type { MngService } from './mngService.js';

export function registerCommands(
    context: vscode.ExtensionContext,
    treeProvider: AgentTreeProvider,
    mngService: MngService,
): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('mng.refresh', () => treeProvider.refresh()),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mng.openPRSideBySide', async (node: AgentNode) => {
            if (!node?.pr) {
                vscode.window.showInformationMessage('No PR found for this agent.');
                return;
            }
            const config = getConfig();

            if (config.prOpenMode === 'githubPR') {
                // Check if GitHub PR extension is installed
                const ghPrExt = vscode.extensions.getExtension('GitHub.vscode-pull-request-github');
                if (ghPrExt) {
                    // Trigger their checkout-by-number UI -- user can select the PR
                    await vscode.commands.executeCommand('pr.checkoutByNumber');
                } else {
                    vscode.window.showWarningMessage(
                        'GitHub Pull Requests extension is not installed. Opening in browser instead.',
                    );
                    await vscode.env.openExternal(vscode.Uri.parse(node.pr.url));
                }
            } else {
                // 'external' (default)
                await vscode.env.openExternal(vscode.Uri.parse(node.pr.url));
            }
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mng.openPR', async (node: AgentNode) => {
            if (!node?.pr) return;
            await vscode.env.openExternal(vscode.Uri.parse(node.pr.url));
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mng.connectAgent', async (node: AgentNode) => {
            if (!node?.agent) return;
            await mngService.connectAgent(node.agent.name);
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mng.openAgentUrl', async (node: AgentNode) => {
            if (!node?.agent?.url) return;
            await vscode.env.openExternal(vscode.Uri.parse(node.agent.url));
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mng.stopAgent', async (node: AgentNode) => {
            if (!node?.agent) return;
            const confirm = await vscode.window.showWarningMessage(
                `Stop agent "${node.agent.name}"?`,
                { modal: true },
                'Stop',
            );
            if (confirm !== 'Stop') return;
            try {
                await mngService.stopAgent(node.agent.name);
                vscode.window.showInformationMessage(`Agent "${node.agent.name}" stopped.`);
                await treeProvider.refresh();
            } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : String(err);
                vscode.window.showErrorMessage(`Failed to stop agent: ${msg}`);
            }
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mng.pullFromAgent', async (node: AgentNode) => {
            if (!node?.agent) return;
            await mngService.pullFromAgent(node.agent.name);
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('mng.createAgent', () => {
            const config = getConfig();
            const terminal = vscode.window.createTerminal({ name: 'mng create' });
            terminal.sendText(`${config.uvPath} run mng create`);
            terminal.show();
        }),
    );
}
