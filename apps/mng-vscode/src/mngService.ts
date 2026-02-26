import { execFile } from 'child_process';
import { promisify } from 'util';
import * as vscode from 'vscode';
import { getConfig, getRepoRoot } from './config.js';
import type { MngAgent } from './types.js';

const execFileAsync = promisify(execFile);

export class MngService {
    async listAgents(): Promise<MngAgent[]> {
        const config = getConfig();
        const repoRoot = getRepoRoot();

        try {
            const { stdout } = await execFileAsync(
                config.uvPath,
                ['run', 'mng', 'list', '--format', 'json'],
                { cwd: repoRoot, timeout: 30000 },
            );

            const data = JSON.parse(stdout);
            return (data.agents || []).map((a: Record<string, unknown>) => parseAgent(a));
        } catch (err: unknown) {
            if (err && typeof err === 'object' && 'code' in err && err.code === 'ENOENT') {
                vscode.window.showWarningMessage(
                    'mng CLI not found. Install it or configure mng.uvPath.',
                );
                return [];
            }
            // Log but don't crash -- return empty list on transient errors
            const channel = vscode.window.createOutputChannel('mng agent viewer');
            channel.appendLine(`Error listing agents: ${err}`);
            return [];
        }
    }

    async connectAgent(agentName: string): Promise<void> {
        const config = getConfig();
        const terminal = vscode.window.createTerminal({
            name: `mng: ${agentName}`,
            shellPath: '/bin/bash',
            shellArgs: ['-c', `${config.uvPath} run mng connect ${agentName}`],
        });
        terminal.show();
    }

    async stopAgent(agentName: string): Promise<void> {
        const config = getConfig();
        const repoRoot = getRepoRoot();
        await execFileAsync(config.uvPath, ['run', 'mng', 'stop', agentName], {
            cwd: repoRoot,
            timeout: 30000,
        });
    }

    async pullFromAgent(agentName: string): Promise<void> {
        const config = getConfig();
        const terminal = vscode.window.createTerminal({
            name: `mng pull: ${agentName}`,
            shellPath: '/bin/bash',
            shellArgs: ['-c', `${config.uvPath} run mng pull ${agentName}`],
        });
        terminal.show();
    }
}

export function parseAgent(data: Record<string, unknown>): MngAgent {
    const host = (data.host || {}) as Record<string, unknown>;
    return {
        id: String(data.id ?? ''),
        name: String(data.name ?? ''),
        type: String(data.type ?? ''),
        state: String(data.state ?? '').toLowerCase(),
        branch: data.branch != null ? String(data.branch) : null,
        url: data.url != null ? String(data.url) : null,
        createTime: String(data.create_time ?? ''),
        runtimeSeconds: typeof data.runtime_seconds === 'number' ? data.runtime_seconds : null,
        host: {
            id: String(host.id ?? ''),
            name: String(host.name ?? ''),
            providerName: String(host.provider_name ?? ''),
            state: String(host.state ?? ''),
        },
        labels: (data.labels || {}) as Record<string, string>,
    };
}
