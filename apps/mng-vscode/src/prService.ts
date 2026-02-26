import { execFile } from 'child_process';
import { promisify } from 'util';
import { getConfig, getRepoRoot } from './config.js';
import type { PrInfo } from './types.js';

const execFileAsync = promisify(execFile);

interface CacheEntry {
    pr: PrInfo | null;
    fetchedAt: number;
}

const CACHE_TTL_MS = 60_000;

export class PrService {
    private cache = new Map<string, CacheEntry>();

    async getPrsForBranches(branches: string[]): Promise<Map<string, PrInfo>> {
        const result = new Map<string, PrInfo>();
        const uncached: string[] = [];

        for (const branch of branches) {
            const cached = this.cache.get(branch);
            if (cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS) {
                if (cached.pr) result.set(branch, cached.pr);
            } else {
                uncached.push(branch);
            }
        }

        if (uncached.length === 0) return result;

        try {
            const config = getConfig();
            const repoRoot = getRepoRoot();

            const { stdout } = await execFileAsync(config.ghPath, [
                'pr', 'list',
                '--state', 'all',
                '--limit', '100',
                '--json', 'number,title,state,url,headRefName,isDraft,additions,deletions,reviewDecision',
            ], { cwd: repoRoot, timeout: 15000 });

            const prs = JSON.parse(stdout) as Record<string, unknown>[];
            const prByBranch = new Map<string, Record<string, unknown>>();
            for (const pr of prs) {
                prByBranch.set(String(pr.headRefName), pr);
            }

            for (const branch of uncached) {
                const pr = prByBranch.get(branch);
                if (pr) {
                    const prInfo: PrInfo = {
                        number: Number(pr.number),
                        title: String(pr.title),
                        state: String(pr.state).toLowerCase(),
                        url: String(pr.url),
                        branch: String(pr.headRefName),
                        isDraft: Boolean(pr.isDraft),
                        additions: Number(pr.additions ?? 0),
                        deletions: Number(pr.deletions ?? 0),
                        reviewDecision: pr.reviewDecision != null ? String(pr.reviewDecision) : null,
                    };
                    result.set(branch, prInfo);
                    this.cache.set(branch, { pr: prInfo, fetchedAt: Date.now() });
                } else {
                    this.cache.set(branch, { pr: null, fetchedAt: Date.now() });
                }
            }
        } catch {
            // gh not installed or not in a git repo -- silently degrade
        }

        return result;
    }

    clearCache(): void {
        this.cache.clear();
    }
}
