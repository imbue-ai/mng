import { describe, it, expect } from 'vitest';
import { AgentNode } from './agentNode.js';
import type { MngAgent, PrInfo } from './types.js';

function makeAgent(overrides: Partial<MngAgent> = {}): MngAgent {
    return {
        id: 'agent-1',
        name: 'test-agent',
        type: 'claude',
        state: 'running',
        branch: 'mng/test-agent',
        url: 'https://example.com/agent',
        createTime: '2025-01-15T10:00:00Z',
        runtimeSeconds: 600,
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

function makePr(overrides: Partial<PrInfo> = {}): PrInfo {
    return {
        number: 42,
        title: 'Fix the thing',
        state: 'open',
        url: 'https://github.com/org/repo/pull/42',
        branch: 'mng/test-agent',
        isDraft: false,
        additions: 10,
        deletions: 5,
        reviewDecision: null,
        ...overrides,
    };
}

describe('AgentNode', () => {
    it('sets label to the agent name', () => {
        const node = new AgentNode(makeAgent({ name: 'my-cool-agent' }), null);
        expect(node.label).toBe('my-cool-agent');
    });

    describe('description', () => {
        it('shows PR info when PR exists', () => {
            const node = new AgentNode(makeAgent(), makePr({ number: 99, title: 'Add feature' }));
            expect(node.description).toBe('PR #99: Add feature');
        });

        it('shows branch when no PR but branch exists', () => {
            const node = new AgentNode(makeAgent({ branch: 'mng/some-branch' }), null);
            expect(node.description).toBe('mng/some-branch');
        });

        it('shows type when no branch and no PR', () => {
            const node = new AgentNode(makeAgent({ branch: null }), null);
            expect(node.description).toBe('claude');
        });
    });

    describe('contextValue', () => {
        it('includes hasPR when PR present', () => {
            const node = new AgentNode(makeAgent(), makePr());
            expect(node.contextValue).toContain('hasPR');
        });

        it('does not include hasPR when no PR', () => {
            const node = new AgentNode(makeAgent(), null);
            expect(node.contextValue).not.toContain('hasPR');
        });

        it('includes running when agent is running', () => {
            const node = new AgentNode(makeAgent({ state: 'running' }), null);
            expect(node.contextValue).toContain('running');
        });

        it('includes hasUrl when agent has a URL', () => {
            const node = new AgentNode(makeAgent({ url: 'https://example.com' }), null);
            expect(node.contextValue).toContain('hasUrl');
        });

        it('does not include hasUrl when agent URL is null', () => {
            const node = new AgentNode(makeAgent({ url: null }), null);
            expect(node.contextValue).not.toContain('hasUrl');
        });

        it('includes hasBranch when agent has a branch', () => {
            const node = new AgentNode(makeAgent({ branch: 'mng/x' }), null);
            expect(node.contextValue).toContain('hasBranch');
        });
    });

    describe('icon', () => {
        it('uses vm-running icon for running state', () => {
            const node = new AgentNode(makeAgent({ state: 'running' }), null);
            expect(node.iconPath.id).toBe('vm-running');
        });

        it('uses debug-stop icon for stopped state', () => {
            const node = new AgentNode(makeAgent({ state: 'stopped' }), null);
            expect(node.iconPath.id).toBe('debug-stop');
        });

        it('uses watch icon for waiting state', () => {
            const node = new AgentNode(makeAgent({ state: 'waiting' }), null);
            expect(node.iconPath.id).toBe('watch');
        });

        it('uses check icon for done state', () => {
            const node = new AgentNode(makeAgent({ state: 'done' }), null);
            expect(node.iconPath.id).toBe('check');
        });

        it('uses replace icon for replaced state', () => {
            const node = new AgentNode(makeAgent({ state: 'replaced' }), null);
            expect(node.iconPath.id).toBe('replace');
        });

        it('uses question icon for unknown state', () => {
            const node = new AgentNode(makeAgent({ state: 'unknown-state' }), null);
            expect(node.iconPath.id).toBe('question');
        });
    });

    describe('click command', () => {
        it('sets command to openPRSideBySide when PR exists', () => {
            const node = new AgentNode(makeAgent(), makePr());
            expect(node.command).toBeDefined();
            expect(node.command!.command).toBe('mng.openPRSideBySide');
        });

        it('does not set command when no PR', () => {
            const node = new AgentNode(makeAgent(), null);
            expect(node.command).toBeUndefined();
        });
    });

    describe('tooltip', () => {
        it('includes agent name and state', () => {
            const node = new AgentNode(makeAgent({ name: 'foo', state: 'running' }), null);
            expect(node.tooltip.value).toContain('**foo**');
            expect(node.tooltip.value).toContain('RUNNING');
        });

        it('includes PR details when PR exists', () => {
            const node = new AgentNode(makeAgent(), makePr({ number: 42, title: 'Fix thing', additions: 10, deletions: 5 }));
            expect(node.tooltip.value).toContain('PR #42: Fix thing');
            expect(node.tooltip.value).toContain('+10 -5');
        });

        it('includes runtime in minutes when runtime is present', () => {
            const node = new AgentNode(makeAgent({ runtimeSeconds: 180 }), null);
            expect(node.tooltip.value).toContain('Runtime: 3m');
        });
    });
});
