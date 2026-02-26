import { describe, it, expect } from 'vitest';
import { parseAgent } from './mngService.js';

describe('parseAgent', () => {
    it('parses a complete agent JSON object with all fields', () => {
        const data = {
            id: 'agent-123',
            name: 'my-agent',
            type: 'claude',
            state: 'Running',
            branch: 'mng/my-agent',
            url: 'https://example.com/agent',
            create_time: '2025-01-15T10:00:00Z',
            runtime_seconds: 3600,
            host: {
                id: 'host-456',
                name: 'dev-box',
                provider_name: 'aws',
                state: 'running',
            },
            labels: { task: 'fix-bug', priority: 'high' },
        };

        const agent = parseAgent(data);

        expect(agent.id).toBe('agent-123');
        expect(agent.name).toBe('my-agent');
        expect(agent.type).toBe('claude');
        expect(agent.state).toBe('running');
        expect(agent.branch).toBe('mng/my-agent');
        expect(agent.url).toBe('https://example.com/agent');
        expect(agent.createTime).toBe('2025-01-15T10:00:00Z');
        expect(agent.runtimeSeconds).toBe(3600);
        expect(agent.host).toEqual({
            id: 'host-456',
            name: 'dev-box',
            providerName: 'aws',
            state: 'running',
        });
        expect(agent.labels).toEqual({ task: 'fix-bug', priority: 'high' });
    });

    it('parses an agent with null branch, url, and runtime_seconds', () => {
        const data = {
            id: 'agent-789',
            name: 'bare-agent',
            type: 'codex',
            state: 'done',
            branch: null,
            url: null,
            create_time: '2025-01-16T12:00:00Z',
            runtime_seconds: null,
            host: {
                id: 'host-001',
                name: 'h1',
                provider_name: 'local',
                state: 'stopped',
            },
            labels: {},
        };

        const agent = parseAgent(data);

        expect(agent.branch).toBeNull();
        expect(agent.url).toBeNull();
        expect(agent.runtimeSeconds).toBeNull();
    });

    it('parses with missing host data', () => {
        const data = {
            id: 'agent-abc',
            name: 'no-host-agent',
            type: 'claude',
            state: 'stopped',
        };

        const agent = parseAgent(data);

        expect(agent.host).toEqual({
            id: '',
            name: '',
            providerName: '',
            state: '',
        });
    });

    it('lowercases the state string', () => {
        const data = {
            id: 'x',
            name: 'x',
            type: 'x',
            state: 'RUNNING',
            host: {},
        };

        expect(parseAgent(data).state).toBe('running');
    });

    it('preserves labels as-is', () => {
        const data = {
            id: 'x',
            name: 'x',
            type: 'x',
            state: 'done',
            host: {},
            labels: { CamelCase: 'Value', 'with-dash': '123' },
        };

        const agent = parseAgent(data);
        expect(agent.labels).toEqual({ CamelCase: 'Value', 'with-dash': '123' });
    });

    it('handles missing optional fields with defaults', () => {
        const data = {};

        const agent = parseAgent(data);

        expect(agent.id).toBe('');
        expect(agent.name).toBe('');
        expect(agent.type).toBe('');
        expect(agent.state).toBe('');
        expect(agent.branch).toBeNull();
        expect(agent.url).toBeNull();
        expect(agent.createTime).toBe('');
        expect(agent.runtimeSeconds).toBeNull();
        expect(agent.labels).toEqual({});
    });
});
