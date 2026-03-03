# Refactoring the Listing / Discovery System

## Problem Statement

The code that handles listing hosts and agents is correct and fast, but its organization is confusing. The functionality is spread across `api/list.py`, `interfaces/provider_instance.py`, and provider implementations, with unclear naming that obscures what each piece does.

There are two fundamentally distinct operations happening:

1. **Discovery**: Get lightweight references (HostReference + AgentReference) for all hosts and agents across all providers. This is needed by ~17 callers (find, connect, destroy, exec, message, rename, etc.) that just need to resolve a name/ID to a reference.

2. **Enrichment**: Get full detailed info (HostInfo + AgentInfo) for specific hosts and agents. This is only needed by the `mng list` command (and the kanpan/schedule plugins) for display purposes.

Currently these two operations are interleaved in `api/list.py`, and the naming does not make the distinction clear.

## Current State

### Key functions and where they live

| Function | File | What it does |
|---|---|---|
| `load_all_agents_grouped_by_host()` | `api/list.py` | Queries all providers in parallel, returns `dict[HostReference, list[AgentReference]]`. Used by 17+ callers. |
| `load_agent_refs()` | `interfaces/provider_instance.py` | Per-provider: returns `dict[HostReference, list[AgentReference]]`. Default impl calls `list_hosts()` then `get_agent_references()` per host. Modal overrides for speed. |
| `list_hosts()` | `interfaces/provider_instance.py` | Abstract. Returns `list[HostInterface]` for the provider. |
| `build_host_listing_data()` | `interfaces/provider_instance.py` | Per-provider optimization hook for enrichment. Returns `tuple[HostInfo, list[AgentInfo]]` or None to fall back. Modal overrides. |
| `_assemble_host_info()` | `api/list.py` | Builds full HostInfo + AgentInfo for a host. Tries `build_host_listing_data()` first, falls back to per-field collection. Despite the name, assembles both host AND agent info. |
| `_process_host_for_agent_listing()` | `api/list.py` | Thin error-handling wrapper around `_assemble_host_info()`. |
| `_process_provider_for_host_listing()` | `api/list.py` | Calls `load_agent_refs()` on a single provider, merges results. |
| `list_agents()` | `api/list.py` | Main entry point for `mng list`. Orchestrates discovery + enrichment + filtering. |

### Naming problems

- **`load_agent_refs`**: Sounds like it loads only agent refs, but it loads both host AND agent refs.
- **`_list_all_host_and_agent_records`**: Modal-specific name that leaks the "records on volume" implementation detail. Uses raw `dict[str, Any]` types.
- **`build_host_listing_data`**: Vague. What it actually does is enrich a host reference into full HostInfo + AgentInfo.
- **`_assemble_host_info`**: Assembles both host AND agent info, not just host info.
- **`load_all_agents_grouped_by_host`**: Accurate but long. More importantly, it lives in `api/list.py` despite being a general-purpose discovery function.
- **`_process_host_for_agent_listing`** vs **`_process_provider_for_host_listing`**: Nearly identical names doing different things.

### Structural problems

- `api/list.py` contains both the `mng list` command logic AND the general-purpose discovery function (`load_all_agents_grouped_by_host`), so 17 files import from `api/list.py` even though they have nothing to do with listing.
- `_assemble_host_info` is ~200 lines doing too many things: get host object, build SSH info, build HostInfo, get agents, build AgentInfo per agent, apply filters, append to results.
- The "enrichment" code in `api/list.py` should arguably live closer to the provider interface, since providers are the ones who know how to efficiently collect full data.

## Proposal

### Step 1: Separate discovery from enrichment at the module level

Move the general-purpose discovery function out of `api/list.py` into a new module `api/discover.py` (or just keep it in `api/find.py`, which already does resolution):

**Option A: New `api/discover.py` module**

```
api/discover.py:
    discover_all_hosts_and_agents(mng_ctx, ...) -> dict[HostReference, list[AgentReference]]

api/list.py:
    list_agents(mng_ctx, ...) -> ListResult  (uses discover_all_hosts_and_agents internally)
```

**Option B: Move into `api/find.py`**

Since `api/find.py` already has the resolution utilities that operate on `dict[HostReference, list[AgentReference]]`, and it's already imported by most of the callers:

```
api/find.py:
    discover_all_hosts_and_agents(mng_ctx, ...) -> dict[HostReference, list[AgentReference]]
    resolve_source_location(...)  # existing
    find_and_maybe_start_agent_by_name_or_id(...)  # existing (from agent_utils.py)

api/list.py:
    list_agents(mng_ctx, ...) -> ListResult
```

**Recommendation**: Option A is cleaner. The discovery function is a distinct concern from "finding a specific agent". It's also used by many callers that don't need any of the find/resolve logic.

### Step 2: Rename provider methods for clarity

On `ProviderInstanceInterface`:

| Current name | Proposed name | Rationale |
|---|---|---|
| `load_agent_refs(cg, include_destroyed)` | `discover_hosts_and_agents(cg, include_destroyed)` | Makes it clear this discovers both hosts and agents, not just agent refs |
| `build_host_listing_data(host_ref, agent_refs)` | `get_host_and_agent_details(host_ref, agent_refs)` | Describes what it returns, not what it's "for" |
| `list_hosts(cg, include_destroyed)` | `list_hosts(cg, include_destroyed)` | This name is fine as-is |

Alternative names considered:
- `discover_hosts_and_agents` could also be `list_host_and_agent_refs` -- "list" fits the naming convention of `list_hosts`, though "discover" better conveys that this is a lightweight enumeration rather than a full data fetch.
- `get_host_and_agent_details` could also be `enrich_host_and_agents` or `collect_host_and_agent_info` -- "get" is simplest and follows the convention of other methods on the interface like `get_host`, `get_host_resources`, `get_host_tags`.

### Step 3: Rename internal functions in `api/list.py`

| Current name | Proposed name | Rationale |
|---|---|---|
| `_assemble_host_info` | `_collect_and_emit_agent_details_for_host` | Describes both what it does (collects details) and the scope (per-host). "Emit" because it fires callbacks and appends to result. |
| `_process_host_for_agent_listing` | `_process_host_with_error_handling` | Makes clear this is just an error-handling wrapper |
| `_process_provider_for_host_listing` | `_discover_provider_hosts_and_agents` | What it actually does |
| `_process_provider_streaming` | `_discover_and_process_provider_streaming` | Clarifies two phases |

These internal names matter less than the public API, but they still help readability. Alternative: since `_assemble_host_info` is very long, we could break it into:
- `_build_host_info_from_online_host(host, host_ref)` -> HostInfo
- `_build_agent_info_from_online_agent(agent, host_info, activity_config, ssh_activity)` -> AgentInfo
- `_build_agent_info_from_offline_ref(agent_ref, host_info)` -> AgentInfo

This would make the code much more readable and testable.

### Step 4: Consider a typed return for discovery

Currently `discover_all_hosts_and_agents` returns `tuple[dict[HostReference, list[AgentReference]], list[BaseProviderInstance]]`. The tuple-of-two is slightly awkward.

Option: Create a `DiscoveryResult` frozen model:

```python
class DiscoveryResult(FrozenModel):
    """Result of discovering all hosts and agents across providers."""

    agent_refs_by_host: dict[HostReference, list[AgentReference]] = Field(
        description="Agent references grouped by their host"
    )
    providers: list[BaseProviderInstance] = Field(
        description="Provider instances that were queried"
    )
```

This would make it clearer what callers are working with. Most callers only need `agent_refs_by_host`, so the providers field is already somewhat awkward -- but at least with a named type it's self-documenting.

### Step 5 (optional): Move enrichment closer to the provider

Currently the default enrichment logic (the fallback when `build_host_listing_data` returns None) lives in `api/list.py:_assemble_host_info`. This is ~150 lines of code that builds HostInfo + AgentInfo by calling many methods on the host object.

We could move this default implementation into `ProviderInstanceInterface.get_host_and_agent_details()` itself (as the default implementation, not returning None). Then `api/list.py` would simply call the provider method for every host, without needing to know about the fallback logic.

Pros:
- Provider owns all data-fetching logic
- `api/list.py` becomes a pure orchestrator (parallel dispatch + filtering + streaming)
- Easier for new providers to understand what they need to implement

Cons:
- The default implementation needs access to `Host` (the concrete class), which creates a dependency from the interface layer to the implementation layer
- Slight coupling increase

This is a larger change and could be done separately.

## Summary of recommended changes

1. **Create `api/discover.py`** with `discover_all_hosts_and_agents()` (moved from `api/list.py`)
2. **Rename `load_agent_refs`** to `discover_hosts_and_agents` on `ProviderInstanceInterface`
3. **Rename `build_host_listing_data`** to `get_host_and_agent_details` on `ProviderInstanceInterface`
4. **Rename internal functions** in `api/list.py` for clarity
5. **Break up `_assemble_host_info`** into smaller focused functions
6. (Optional) Create `DiscoveryResult` type for the return value
7. (Optional, separate PR) Move default enrichment logic into the provider interface

Steps 1-5 are safe, mechanical refactors that can be done incrementally (each as a separate commit) with no behavioral changes.

## Appendix: Naming the data types

The current type names (`HostReference`/`AgentReference` vs `HostInfo`/`AgentInfo`) don't clearly convey the lightweight-discovery-result vs full-detailed-data distinction. Here are the options considered:

### Option 1: DiscoveredHost/DiscoveredAgent + HostDetails/AgentDetails (recommended)

| Current | Discovery (lightweight) | Full |
|---|---|---|
| `HostReference` | `DiscoveredHost` | `HostDetails` |
| `AgentReference` | `DiscoveredAgent` | `AgentDetails` |

Pros:
- Directly ties to the "discovery" operation. `discover_hosts_and_agents()` returns `DiscoveredHost`/`DiscoveredAgent` -- the naming tells you where the data came from.
- Makes the distinction visceral: "discovered" immediately conveys "I found this thing but haven't deeply inspected it yet".
- `Details` is clear and conventional for the enriched version.

Cons:
- Adjective-noun pattern is slightly unusual for data types in this codebase (most are Noun-Qualifier like `HostInfo`).

The provider methods would then read:

```python
# Discovery
def discover_hosts_and_agents(
    cg, include_destroyed,
) -> dict[DiscoveredHost, list[DiscoveredAgent]]: ...

# Enrichment
def get_host_and_agent_details(
    host: DiscoveredHost, agents: Sequence[DiscoveredAgent],
) -> tuple[HostDetails, list[AgentDetails]] | None: ...
```

### Option 2: HostSummary/AgentSummary + HostDetails/AgentDetails

| Current | Discovery (lightweight) | Full |
|---|---|---|
| `HostReference` | `HostSummary` | `HostDetails` |
| `AgentReference` | `AgentSummary` | `AgentDetails` |

Pros:
- Very clear what each is. "Summary" implies "I know the basics". "Details" implies "I know everything".
- Follows the Noun-Qualifier pattern used elsewhere in the codebase.

Cons:
- "Summary" might imply a summarized/reduced version of the full data, when really it's a fundamentally different data source (certified/offline data vs live-queried data).

### Option 3: HostRecord/AgentRecord + HostDetails/AgentDetails

| Current | Discovery (lightweight) | Full |
|---|---|---|
| `HostReference` | `HostRecord` | `HostDetails` |
| `AgentReference` | `AgentRecord` | `AgentDetails` |

Pros:
- "Record" conveys stored/persisted data. "Details" conveys live-queried data.

Cons:
- "Record" is already used by Modal's `HostRecord` (the volume-persisted data structure). Would need to rename that to `ModalHostRecord` or `PersistedHostData`.

### Option 4: HostEntry/AgentEntry + HostDetails/AgentDetails

| Current | Discovery (lightweight) | Full |
|---|---|---|
| `HostReference` | `HostEntry` | `HostDetails` |
| `AgentReference` | `AgentEntry` | `AgentDetails` |

Pros:
- "Entry" is like "a row in a directory listing" -- you know it exists and its basic attributes.

Cons:
- "Entry" is generic and doesn't convey the discovery context.

### Option 5: HostIdentity/AgentIdentity + HostDetails/AgentDetails

| Current | Discovery (lightweight) | Full |
|---|---|---|
| `HostReference` | `HostIdentity` | `HostDetails` |
| `AgentReference` | `AgentIdentity` | `AgentDetails` |

Pros:
- Very precise about what the lightweight version is -- it identifies the thing.

Cons:
- `AgentReference` contains more than just identity (it has certified_data with work_dir, command, labels, etc.), so "Identity" undersells it.

### Recommendation

Option 1 (`DiscoveredHost`/`DiscoveredAgent` + `HostDetails`/`AgentDetails`) best conveys the relationship between the discovery operation and its output. Option 2 (`HostSummary`/`AgentSummary`) is the runner-up if the adjective-noun pattern feels too unusual.
