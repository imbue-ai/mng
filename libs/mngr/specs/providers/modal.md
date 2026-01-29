# Modal Provider Spec

## Metadata Storage

Agent metadata is stored as Modal sandbox tags. When an agent is created, mngr sets tags on the sandbox:

```python
sandbox.tags = {
    "mngr.agent-id": "<agent-id>",
    "mngr.agent-name": "<name>",
    "mngr.agent-type": "<type>",
    "mngr.tags": "<json-encoded-tags>",
    "mngr.parent-id": "<parent-agent-id>",
    "mngr.created-at": "<iso-timestamp>",
}
```

Tags are preserved across sandbox stop/start cycles and in snapshots.

## Host Discovery

mngr discovers Modal hosts by listing sandboxes with the `mngr.agent-id` tag.

## Agent Self-Management [future]

Modal sandboxes are isolated environments that don't have direct access to Modal's control plane APIs. To allow agents running inside Modal sandboxes to pause or stop themselves, mngr must deploy a Modal function that agents can call.

This function acts as a bridge between the sandboxed agent and Modal's control plane, allowing agents to:
- Request their own sandbox to be paused
- Request their own sandbox to be stopped
- Query their own sandbox status

This approach avoids injecting Modal credentials directly into the sandbox, maintaining security isolation.

## Snapshots

Modal provides native snapshot support. Snapshots are fully incremental since the last snapshot.

To minimize the risk of work loss if a sandbox crashes, Modal sandshots should be taken fairly frequently while the agent is working. The frequency should be configurable but default to a reasonable interval (e.g., every 15-30 minutes of active work).

Note: Automatic periodic snapshots [future] are not yet implemented (currently only on-demand snapshots work).
