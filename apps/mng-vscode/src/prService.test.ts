import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PrService } from './prService.js';

// Mock child_process to prevent real shell execution
vi.mock('child_process', () => ({
    execFile: vi.fn(),
}));

// Mock config to return deterministic values
vi.mock('./config.js', () => ({
    getConfig: () => ({
        ghPath: 'gh',
        uvPath: 'uv',
        pollInterval: 10,
        repoRoot: '',
        prOpenMode: 'external',
    }),
    getRepoRoot: () => '/fake/repo',
}));

import { execFile } from 'child_process';

function mockExecFile(stdout: string) {
    (execFile as unknown as ReturnType<typeof vi.fn>).mockImplementation(
        (_cmd: string, _args: string[], _opts: any, cb?: Function) => {
            // promisify(execFile) calls execFile(cmd, args, opts) and returns a promise
            // But the actual mock for promisify needs to handle the callback pattern
            if (cb) {
                cb(null, { stdout });
            }
            return undefined;
        },
    );
}

describe('PrService', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it('returns cached data for previously fetched branches', async () => {
        const prData = [
            {
                number: 42,
                title: 'Fix the thing',
                state: 'OPEN',
                url: 'https://github.com/org/repo/pull/42',
                headRefName: 'mng/fix-thing',
                isDraft: false,
                additions: 10,
                deletions: 5,
                reviewDecision: null,
            },
        ];
        mockExecFile(JSON.stringify(prData));

        const service = new PrService();

        // First call fetches from gh
        const result1 = await service.getPrsForBranches(['mng/fix-thing']);
        expect(result1.has('mng/fix-thing')).toBe(true);
        expect(result1.get('mng/fix-thing')!.number).toBe(42);

        // Second call should use cache (no new execFile call needed)
        const callCountAfterFirst = (execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
        const result2 = await service.getPrsForBranches(['mng/fix-thing']);
        expect(result2.has('mng/fix-thing')).toBe(true);
        expect(result2.get('mng/fix-thing')!.number).toBe(42);

        // execFile should NOT have been called again
        expect((execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(callCountAfterFirst);
    });

    it('cache expires after TTL (60 seconds)', async () => {
        const prData = [
            {
                number: 1,
                title: 'PR 1',
                state: 'OPEN',
                url: 'https://github.com/org/repo/pull/1',
                headRefName: 'branch-a',
                isDraft: false,
                additions: 1,
                deletions: 0,
                reviewDecision: null,
            },
        ];
        mockExecFile(JSON.stringify(prData));

        const service = new PrService();

        // First call
        await service.getPrsForBranches(['branch-a']);
        const callCountAfterFirst = (execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length;

        // Advance past the TTL
        vi.advanceTimersByTime(61_000);

        // Second call should re-fetch because cache expired
        await service.getPrsForBranches(['branch-a']);
        expect((execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callCountAfterFirst);
    });

    it('returns empty map for empty branches array', async () => {
        const service = new PrService();
        const result = await service.getPrsForBranches([]);
        expect(result.size).toBe(0);
    });

    it('clearCache empties the cache', async () => {
        const prData = [
            {
                number: 7,
                title: 'Some PR',
                state: 'OPEN',
                url: 'https://github.com/org/repo/pull/7',
                headRefName: 'branch-b',
                isDraft: false,
                additions: 3,
                deletions: 2,
                reviewDecision: 'APPROVED',
            },
        ];
        mockExecFile(JSON.stringify(prData));

        const service = new PrService();
        await service.getPrsForBranches(['branch-b']);
        const callCountAfterFirst = (execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length;

        service.clearCache();

        // After clearing cache, fetching same branch should re-invoke execFile
        await service.getPrsForBranches(['branch-b']);
        expect((execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callCountAfterFirst);
    });

    it('caches null for branches with no matching PR', async () => {
        mockExecFile(JSON.stringify([]));

        const service = new PrService();

        const result = await service.getPrsForBranches(['no-such-branch']);
        expect(result.has('no-such-branch')).toBe(false);

        // Second call should still use cache (no re-fetch)
        const callCount = (execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
        const result2 = await service.getPrsForBranches(['no-such-branch']);
        expect(result2.has('no-such-branch')).toBe(false);
        expect((execFile as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBe(callCount);
    });
});
