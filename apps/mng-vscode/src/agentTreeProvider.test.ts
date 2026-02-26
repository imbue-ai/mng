import { describe, it, expect, beforeEach } from 'vitest';
import { AgentTreeProvider } from './agentTreeProvider.js';
import type { MngAgent, PrInfo } from './types.js';
import type { MngService } from './mngService.js';
import type { PrService } from './prService.js';

function makeAgent(overrides: Partial<MngAgent> = {}): MngAgent {
    return {
        id: 'agent-1',
        name: 'test-agent',
        type: 'claude',
        state: 'running',
        branch: 'mng/test-agent',
        url: null,
        createTime: '2025-01-15T10:00:00Z',
        runtimeSeconds: null,
        host: {
            id: 'host-1',
            name: 'dev-box',
            providerName: 'aws',
            state: 'running',
        },
        labels: {},
        ...overrides,
    };
}

function createMockMngService(agents: MngAgent[]): MngService {
    return {
        listAgents: async () => agents,
        connectAgent: async () => {},
        stopAgent: async () => {},
        pullFromAgent: async () => {},
    } as unknown as MngService;
}

function createMockPrService(prs: Map<string, PrInfo>): PrService {
    return {
        getPrsForBranches: async () => prs,
        clearCache: () => {},
    } as unknown as PrService;
}

describe('AgentTreeProvider', () => {
    describe('getChildren', () => {
        it('returns empty array when no agents', async () => {
            const provider = new AgentTreeProvider(
                createMockMngService([]),
                createMockPrService(new Map()),
            );
            await provider.refresh();
            const children = provider.getChildren();
            expect(children).toEqual([]);
        });

        it('returns empty array for child elements (flat tree)', async () => {
            const provider = new AgentTreeProvider(
                createMockMngService([makeAgent()]),
                createMockPrService(new Map()),
            );
            await provider.refresh();
            const children = provider.getChildren();
            // Passing a child node should return empty
            expect(provider.getChildren(children[0])).toEqual([]);
        });

        it('sorts agents by state priority: running, waiting, stopped, done, replaced', async () => {
            const agents = [
                makeAgent({ id: '1', name: 'a-done', state: 'done' }),
                makeAgent({ id: '2', name: 'b-running', state: 'running' }),
                makeAgent({ id: '3', name: 'c-waiting', state: 'waiting' }),
                makeAgent({ id: '4', name: 'd-stopped', state: 'stopped' }),
                makeAgent({ id: '5', name: 'e-replaced', state: 'replaced' }),
            ];

            const provider = new AgentTreeProvider(
                createMockMngService(agents),
                createMockPrService(new Map()),
            );
            await provider.refresh();
            const children = provider.getChildren();

            const states = children.map(c => c.agent.state);
            expect(states).toEqual(['running', 'waiting', 'stopped', 'done', 'replaced']);
        });

        it('sorts alphabetically within same state', async () => {
            const agents = [
                makeAgent({ id: '1', name: 'charlie', state: 'running' }),
                makeAgent({ id: '2', name: 'alpha', state: 'running' }),
                makeAgent({ id: '3', name: 'bravo', state: 'running' }),
            ];

            const provider = new AgentTreeProvider(
                createMockMngService(agents),
                createMockPrService(new Map()),
            );
            await provider.refresh();
            const children = provider.getChildren();

            const names = children.map(c => c.agent.name);
            expect(names).toEqual(['alpha', 'bravo', 'charlie']);
        });

        it('attaches PR info to agents with matching branches', async () => {
            const agents = [
                makeAgent({ id: '1', name: 'with-pr', state: 'running', branch: 'mng/with-pr' }),
                makeAgent({ id: '2', name: 'no-pr', state: 'running', branch: 'mng/no-pr' }),
            ];
            const prs = new Map<string, PrInfo>([
                ['mng/with-pr', {
                    number: 10,
                    title: 'My PR',
                    state: 'open',
                    url: 'https://github.com/org/repo/pull/10',
                    branch: 'mng/with-pr',
                    isDraft: false,
                    additions: 5,
                    deletions: 2,
                    reviewDecision: null,
                }],
            ]);

            const provider = new AgentTreeProvider(
                createMockMngService(agents),
                createMockPrService(prs),
            );
            await provider.refresh();
            const children = provider.getChildren();

            const withPr = children.find(c => c.agent.name === 'with-pr')!;
            const noPr = children.find(c => c.agent.name === 'no-pr')!;
            expect(withPr.pr).not.toBeNull();
            expect(withPr.pr!.number).toBe(10);
            expect(noPr.pr).toBeNull();
        });
    });

    describe('getAgentSummary', () => {
        it('returns zeros when no agents', async () => {
            const provider = new AgentTreeProvider(
                createMockMngService([]),
                createMockPrService(new Map()),
            );
            await provider.refresh();
            const summary = provider.getAgentSummary();
            expect(summary).toEqual({ totalAgents: 0, runningAgents: 0, openPRs: 0 });
        });

        it('returns correct counts for mixed agents and PRs', async () => {
            const agents = [
                makeAgent({ id: '1', name: 'a', state: 'running', branch: 'b1' }),
                makeAgent({ id: '2', name: 'b', state: 'running', branch: 'b2' }),
                makeAgent({ id: '3', name: 'c', state: 'done', branch: 'b3' }),
                makeAgent({ id: '4', name: 'd', state: 'stopped', branch: null }),
            ];
            const prs = new Map<string, PrInfo>([
                ['b1', {
                    number: 1, title: 'PR 1', state: 'open', url: '', branch: 'b1',
                    isDraft: false, additions: 0, deletions: 0, reviewDecision: null,
                }],
                ['b2', {
                    number: 2, title: 'PR 2', state: 'open', url: '', branch: 'b2',
                    isDraft: false, additions: 0, deletions: 0, reviewDecision: null,
                }],
                ['b3', {
                    number: 3, title: 'PR 3', state: 'merged', url: '', branch: 'b3',
                    isDraft: false, additions: 0, deletions: 0, reviewDecision: null,
                }],
            ]);

            const provider = new AgentTreeProvider(
                createMockMngService(agents),
                createMockPrService(prs),
            );
            await provider.refresh();
            const summary = provider.getAgentSummary();

            expect(summary.totalAgents).toBe(4);
            expect(summary.runningAgents).toBe(2);
            expect(summary.openPRs).toBe(2);
        });
    });
});
