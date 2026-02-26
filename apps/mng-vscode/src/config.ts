import * as vscode from 'vscode';

export function getConfig() {
    const config = vscode.workspace.getConfiguration('mng');
    return {
        pollInterval: config.get<number>('pollInterval', 10),
        uvPath: config.get<string>('uvPath', 'uv'),
        ghPath: config.get<string>('ghPath', 'gh'),
        repoRoot: config.get<string>('repoRoot', ''),
        prOpenMode: config.get<string>('prOpenMode', 'external') as 'external' | 'githubPR',
    };
}

export function getRepoRoot(): string {
    const configured = getConfig().repoRoot;
    if (configured) return configured;
    const folders = vscode.workspace.workspaceFolders;
    return folders?.[0]?.uri.fsPath || process.cwd();
}
