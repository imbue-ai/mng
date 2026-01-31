# Analysis: Places to Use `get_agent_references` Instead of `get_agents`

## Overview

This document identifies places in the mngr codebase where we could potentially use `get_agent_references()` instead of `get_agents()`, assuming that `AgentReference` is extended to include the agent's `data.json` contents (certified data).

## Background

### Current Types

**`AgentReference`** (lightweight) contains:
- `host_id: HostId`
- `agent_id: AgentId`
- `agent_name: AgentName`
- `provider_name: ProviderInstanceName`

**`AgentInterface`** (full object) adds:
- `agent_type: AgentTypeName`
- `work_dir: Path`
- `create_time: datetime`
- `mngr_ctx: MngrContext`
- `agent_config: AgentTypeConfig`
- Plus many methods for reading/writing state, interacting with the agent, etc.

### Agent `data.json` Contents (Certified Data)

If we include `data.json` in `AgentReference`, we would have access to:
- `id`, `name` (already in AgentRef)
- `type` (agent type)
- `work_dir` (working directory path)
- `command` (the command used to start the agent)
- `create_time` (creation timestamp)
- `start_on_boot` (boolean)
- `permissions` (list of permissions)
- `plugin.*` (plugin-specific certified data)
- `initial_message` (optional)
- `additional_commands` (optional list)

### What Would NOT Be Available

Even with `data.json`, we would not have:
- **Reported data**: status, url, start_time, activity times (these are in separate files)
- **Methods requiring host connection**: `send_message`, `is_running`, `get_lifecycle_state`, etc.

---

## Analysis of Current `get_agents()` Usages

### 1. `api/list.py:267` - `list_agents()`

**Current usage:**
```python
agents = cast(OnlineHostInterface, host).get_agents()
```

**What data is actually used:**
- `agent.id`, `agent.name`, `agent.agent_type` (for AgentInfo)
- `agent.get_command()`, `agent.work_dir`, `agent.create_time`
- `agent.get_is_start_on_boot()`
- `agent.get_lifecycle_state()` (REQUIRES HOST)
- `agent.get_reported_status()` (REQUIRES HOST)
- `agent.get_reported_url()` (REQUIRES HOST)
- `agent.get_reported_start_time()` (REQUIRES HOST)
- `agent.runtime_seconds` (REQUIRES HOST)
- `agent.get_reported_activity_time(...)` (REQUIRES HOST)

**Simplification potential:** PARTIAL
- The code already handles stopped hosts by using persisted data (lines 275-316)
- Most of the data for the AgentInfo could come from an enhanced AgentRef
- However, reported data (status, url, activity times) still requires host access
- Could simplify the "find agent in list" pattern

**Decision:** Don't mess with this--fixed in another commit.

---

### 2. `api/find.py:237` - `resolve_source_location()`

**Current usage:**
```python
for agent in online_host.get_agents():
    if agent.id == resolved_agent.agent_id:
        agent_work_dir = agent.work_dir
        break
```

**What data is actually used:**
- `agent.id` (for matching)
- `agent.work_dir` (the actual data needed)

**Simplification potential:** HIGH
- Only needs to find `work_dir` by agent ID
- If `AgentRef` includes `work_dir` from `data.json`, this entire host query could be avoided
- Would allow this to work for offline hosts too

**Decision:** ensure that work_dir is included in AgentReference, then we can use get_agent_references() here instead of get_agents(), and we wouldn't even need an online host.

---

### 3. `api/find.py:338,355` - `find_and_maybe_start_agent_by_name_or_id()`

**Current usage:**
```python
for agent in online_host.get_agents():
    if agent.id == agent_id:  # or agent.id == agent_ref.agent_id
        return agent, online_host
```

**What data is actually used:**
- `agent.id` (for matching)
- Returns the full `AgentInterface` object (caller needs it)

**Simplification potential:** LOW
- The function explicitly returns `(AgentInterface, OnlineHostInterface)`
- Callers need the full agent object to interact with it
- Cannot be simplified without changing the function's contract

**Decision:** ignore this one.

---

### 4. `api/find.py:423` - `load_all_agents_grouped_by_host()`

**Current usage:**
```python
agents = online_host.get_agents()
agent_refs = [
    AgentReference(
        host_id=host.id,
        agent_id=agent.id,
        agent_name=agent.name,
        provider_name=provider.name,
    )
    for agent in agents
]
```

**What data is actually used:**
- `agent.id`, `agent.name` (to build AgentReference)

**Simplification potential:** HIGH
- This function already exists to create agent references
- For online hosts, could call `get_agent_references()` directly instead
- Already handles offline case separately
- Would make the code more consistent

**Decision:** refactor this one to use get_agent_references() instead

---

### 5. `api/gc.py:209` - `gc_machines()`

**Current usage:**
```python
agents = online_host.get_agents()
if len(agents) > 0:
    continue
```

**What data is actually used:**
- Only checks if there are any agents (count > 0)

**Simplification potential:** HIGH
- Just needs to know if the host has any agents
- `get_agent_references()` would work perfectly
- Could even add a `has_agents()` method for this pattern

**Decision:** move to using get_agent_references() here

---

### 6. `api/gc.py:498` - `_get_orphaned_work_dirs()`

**Current usage:**
```python
for agent in host.get_agents():
    active_work_dirs.add(str(agent.work_dir))
```

**What data is actually used:**
- `agent.work_dir` (to build set of active directories)

**Simplification potential:** HIGH
- Only needs work_dir from each agent
- If AgentRef includes `data.json`, `work_dir` would be available
- Could simplify this to use references

**Decision:** ignore, this doesn't make sense--we wouldn't be able to clean up the work dirs of offline hosts anyway.

---

### 7. `api/message.py:103` - `send_message_to_agents()`

**Current usage:**
```python
agents = host.get_agents()
for agent_ref in agent_refs:
    agent = next((a for a in agents if a.id == agent_ref.agent_id), None)
    # ... later uses agent.get_lifecycle_state(), agent.send_message()
```

**What data is actually used:**
- `agent.id` (for matching)
- `agent.name` (for error messages and context)
- `agent.agent_type` (for CEL filtering)
- `agent.host_id` (for CEL filtering)
- `agent.get_lifecycle_state()` (REQUIRES HOST)
- `agent.send_message()` (REQUIRES HOST)

**Simplification potential:** PARTIAL
- The CEL filtering context could use AgentRef + data.json data
- But `get_lifecycle_state()` and `send_message()` require the full agent
- The "find agent in list" pattern could be simplified

**Decision:** ignore--I made a separate fixme for this

---

### 8. `cli/create.py:1253` - `_find_agent_in_host()`

**Current usage:**
```python
for agent in host.get_agents():
    if agent.id == agent_id:
        return agent
```

**What data is actually used:**
- `agent.id` (for matching)
- Returns full `AgentInterface` (caller needs it)

**Simplification potential:** LOW
- Explicitly needs to return the full agent object
- The caller needs to interact with the agent
- Cannot simplify without changing the function contract

**Decision:** ignore.

---

### 9. `cli/destroy.py:305` - `_resolve_agents_to_destroy()`

**Current usage:**
```python
for agent in host.get_agents():
    if agent.id == agent_ref.id:
        agents_to_destroy.append((agent, host))
        break
```

**What data is actually used:**
- `agent.id` (for matching)
- Returns full `AgentInterface` (for destruction)

**Simplification potential:** LOW
- Need full agent object to pass to destroy logic
- Cannot simplify without changing the function contract

**Decision:** ignore, this has been refactored

---

### 10. `hosts/host.py:1805` - `_get_agent_by_id()`

**Current usage:**
```python
agents = self.get_agents()
for agent in agents:
    if agent.id == agent_id:
        return agent
```

**What data is actually used:**
- `agent.id` (for matching)
- Returns full `AgentInterface`

**Simplification potential:** LOW
- Internal helper that returns full agent object
- Used by start/stop agents which need the full object

**Decision:** ignore.

---

### 11. `hosts/host.py:1868` - `get_idle_seconds()`

**Current usage:**
```python
for agent in self.get_agents():
    for activity_type in ActivitySource:
        activity_time = agent.get_reported_activity_time(activity_type)
```

**What data is actually used:**
- `agent.get_reported_activity_time(...)` (REQUIRES HOST)

**Simplification potential:** LOW
- Needs to read reported activity files from the host filesystem
- Cannot work with just reference data

**Decision:** ignore

---

### 12. `hosts/host.py:1884` - `get_permissions()`

**Current usage:**
```python
for agent in self.get_agents():
    agent_permissions = agent.get_permissions()
    permissions.update(str(p) for p in agent_permissions)
```

**What data is actually used:**
- `agent.get_permissions()` (reads from data.json)

**Simplification potential:** HIGH
- `permissions` is certified data stored in `data.json`
- If AgentRef includes `data.json`, this would be available
- Could work with references instead of full agents

**Decision:** please update the AgentReference to include the data.json, and then here we ought to be able to use get_agent_references() instead.

---

## Proposed `AgentReference` Extension

```python
class AgentReference(FrozenModel):
    """Lightweight reference to an agent with certified data from data.json."""

    # Existing fields
    host_id: HostId
    agent_id: AgentId
    agent_name: AgentName
    provider_name: ProviderInstanceName

    # New fields from data.json
    agent_type: AgentTypeName
    work_dir: Path
    command: CommandString | None = None
    create_time: datetime | None = None
    start_on_boot: bool = False
    permissions: tuple[Permission, ...] = ()
    plugin: dict[str, dict[str, Any]] = Field(default_factory=dict)
```

This would provide all certified agent data without requiring host access.

**Decision:** please create these new fields, BUT, create them as @property methods instead, and just add a single field for the data.json contents. That way, even if there are undocumented fields in the future, we can still access them.  You'll want to make it a Mapping so that it fits with the semantics of this object being frozen.
