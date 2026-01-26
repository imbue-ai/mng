# User Activity Tracking via Web - Implementation Plan

This plan covers implementing the **tracking** portion of the user_activity_tracking_via_web plugin. The shutdown/enforcement logic will be implemented separately.

## Summary of Current State

### Existing Activity Infrastructure

The codebase already has activity tracking infrastructure in place:

1. **ActivitySource enum** (`primitives.py:72-81`): Defines activity types: `CREATE`, `BOOT`, `START`, `SSH`, `PROCESS`, `AGENT`, `USER`

2. **Activity storage on hosts** (`hosts/host.py:402-424`):
   - Files stored at `$MNGR_HOST_DIR/activity/<type>` (e.g., `activity/user`, `activity/boot`)
   - `Host.record_activity()` - only allows `BOOT` and `CREATE` (these are "certified" activities set by mngr itself)
   - `Host.get_reported_activity_time()` - returns file mtime as datetime
   - Content is just an ISO timestamp string

3. **Activity storage on agents** (`agents/base_agent.py:339-360`):
   - Files stored at `$MNGR_AGENT_STATE_DIR/activity/<type>`
   - `BaseAgent.record_activity()` - writes JSON `{"time": "<ISO timestamp>"}`
   - `BaseAgent.get_reported_activity_time()` - parses JSON and returns datetime

4. **Idle detection** (`hosts/host.py:1701-1715`):
   - `Host.get_idle_seconds()` - iterates all ActivitySource values, finds latest activity time
   - Returns seconds since last activity (or infinity if no activity)

5. **Activity configuration** (`interfaces/data_types.py:155-163`):
   - `ActivityConfig` - stores `idle_mode`, `idle_timeout_seconds`, `activity_sources`
   - Stored in host's `data.json` as certified data

### What's Missing

The `USER` activity source exists but there's no mechanism to update it from web interfaces. The spec describes:
- JavaScript injection via nginx `sub_filter` to capture user input events
- Nginx endpoint to receive activity pings and update the activity file
- Debounce logic to avoid flooding with requests

## Implementation Plan

### Phase 1: Plugin Configuration

**1.1 Create plugin config class**

Location: `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/config.py`

The plugin config should extend the base `PluginConfig` class from `config/data_types.py`:

```python
from pydantic import Field
from imbue.mngr.config.data_types import PluginConfig

class UserActivityTrackingViaWebConfig(PluginConfig):
    """Configuration for user_activity_tracking_via_web plugin."""

    debounce_ms: int = Field(
        default=1000,
        ge=100,
        le=60000,
        description="Minimum ms between activity reports",
    )
```

Note: The base `PluginConfig` already has an `enabled: bool = True` field.

**1.2 Using the config in MngrConfig**

The existing `MngrConfig` already has:
```python
plugins: dict[PluginName, PluginConfig] = Field(
    default_factory=dict,
    description="Plugin configurations",
)
disabled_plugins: frozenset[str] = Field(
    default_factory=frozenset,
    description="Set of plugin names that were explicitly disabled",
)
```

Users configure in TOML:
```toml
[plugins.user_activity_tracking_via_web]
enabled = true
debounce_ms = 1000
```

**1.3 Register config class with plugin system**

The plugin needs to register its config class so that when the TOML is parsed, the `PluginConfig` dict values get parsed as `UserActivityTrackingViaWebConfig` instead of base `PluginConfig`. This likely requires adding a hookspec/hookimpl for registering plugin config classes, or using a discriminated union pattern.

### Phase 2: Plugin Module Structure

**2.1 Create plugin directory**

```
libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/
    __init__.py
    config.py
    hookimpls.py
    nginx_config.py
    resources/
        activity.js.template
```

**2.2 Implement hookimpls**

The plugin needs to hook into agent provisioning to:
1. Generate `activity.js` with configured debounce_ms
2. Generate nginx config for the plugin
3. Install files to the host

This will use the existing plugin hook system defined in `plugins/hookspecs.py`.

### Phase 3: Nginx Configuration Generation

**3.1 Generate activity.js**

Template location: `resources/activity.js.template`

```javascript
(function() {
  var debounceMs = {{DEBOUNCE_MS}};
  var lastReport = 0;
  var endpoint = '/_mngr/plugin/user_activity_tracking_via_web/activity';

  function report() {
    var now = Date.now();
    if (now - lastReport < debounceMs) return;
    lastReport = now;

    var xhr = new XMLHttpRequest();
    xhr.open('POST', endpoint, true);
    xhr.send();
  }

  document.addEventListener('keydown', report, true);
  document.addEventListener('keypress', report, true);
  document.addEventListener('mousemove', report, true);
  document.addEventListener('click', report, true);
  document.addEventListener('scroll', report, true);
})();
```

**3.2 Generate nginx plugin config**

Location on host: `/etc/mngr/nginx/plugins.d/user_activity_tracking_via_web.conf`

```nginx
# Inject activity tracking script into HTML responses
sub_filter '</head>' '<script src="/_mngr/plugin/user_activity_tracking_via_web/activity.js"></script></head>';
sub_filter_once on;
sub_filter_types text/html;

# Serve the activity tracking script
location = /_mngr/plugin/user_activity_tracking_via_web/activity.js {
    alias /etc/mngr/nginx/plugins.d/user_activity_tracking_via_web/activity.js;
    add_header Content-Type application/javascript;
}

# Handle activity reports - update USER activity file
location = /_mngr/plugin/user_activity_tracking_via_web/activity {
    # Using shell execution via openresty/lua or FastCGI
    # This touches the activity file to update its mtime
    content_by_lua_block {
        local host_dir = os.getenv("MNGR_HOST_DIR")
        if host_dir then
            local f = io.open(host_dir .. "/activity/user", "w")
            if f then
                f:write(os.date("!%Y-%m-%dT%H:%M:%SZ"))
                f:close()
            end
        end
        ngx.status = 204
        ngx.exit(ngx.HTTP_NO_CONTENT)
    }
}
```

### Phase 4: Provisioning Integration

**4.1 Add provisioning hook**

The plugin should use `on_host_created` hook to:
1. Create plugin directory: `/etc/mngr/nginx/plugins.d/user_activity_tracking_via_web/`
2. Write `activity.js` (generated from template with debounce_ms)
3. Write `user_activity_tracking_via_web.conf` to `/etc/mngr/nginx/plugins.d/`
4. Ensure activity directory exists: `$MNGR_HOST_DIR/activity/`
5. Reload nginx configuration

**4.2 Consider dependency on local_port_forwarding_via_frp_and_nginx**

Per the spec, this plugin depends on nginx being present. The implementation should:
- Check if nginx is available (via the port forwarding plugin or otherwise)
- Skip installation gracefully if nginx is not present (with a warning)

### Phase 5: Activity File Updates

**5.1 Ensure HOST-level activity file is used**

The spec indicates activity should be written to `$MNGR_HOST_DIR/activity/user`, which is the **host-level** activity file. This makes sense because:
- Multiple agents can share a host
- User activity on any agent's web interface keeps the whole host alive
- The idle detection system checks host-level activity

**5.2 Verify existing infrastructure handles this**

The current `Host.get_reported_activity_time()` method already reads from `$MNGR_HOST_DIR/activity/<type>` and checks the file mtime. The nginx endpoint just needs to write/touch this file.

### Implementation Order

1. **Create plugin config class** - Define `UserActivityTrackingViaWebConfig` with `enabled` and `debounce_ms` fields
2. **Register config** - Add to `PluginsConfig` in config/data_types.py
3. **Create plugin module** - Set up directory structure and `__init__.py`
4. **Create nginx config generator** - Function to generate the nginx config and activity.js content
5. **Implement hookimpls** - Hook into `on_host_created` to install files
6. **Add file transfer/write during provisioning** - Write files to host during creation
7. **Test manually** - Verify files are created and nginx reloads
8. **Add unit tests** - Test config generation logic
9. **Add integration tests** - Test full flow with actual nginx

### Open Questions

1. **Lua vs FastCGI**: The spec mentions both options. OpenResty (nginx with lua) is simpler but may not be available on all hosts. FastCGI requires running a daemon. **Recommendation**: Start with lua, add FastCGI fallback later if needed.

2. **Authentication**: The activity endpoint should probably require the same auth as other mngr endpoints (cookie or header). The spec shows it in the same nginx config that includes `security.conf`. **Recommendation**: Include auth check in the activity endpoint.

3. **Agent-level vs Host-level**: The spec writes to host-level activity. This is correct for idle detection but means we can't track which agent the user was interacting with. **Recommendation**: Keep as host-level for now; can add agent-level tracking later if needed.

4. **Plugin config registration**: The current `MngrConfig.plugins` is typed as `dict[PluginName, PluginConfig]`, where `PluginConfig` is the base class. This means plugin-specific config fields (like `debounce_ms`) won't be parsed correctly unless we:
   - Add a hookspec for plugins to register their config classes, OR
   - Use a discriminated union pattern with a type field, OR
   - Parse plugin configs manually after initial config load

   **Recommendation**: Research how other plugins handle this, or add a simple hookspec like `register_plugin_config() -> tuple[str, type[PluginConfig]] | None`

5. **Plugin enable/disable**: The existing `MngrConfig` has `disabled_plugins: frozenset[str]` which tracks explicitly disabled plugins. The `PluginConfig.enabled` field also exists. Need to understand how these interact and are used during plugin loading.

### Files to Create/Modify

**New files:**
- `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/__init__.py`
- `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/config.py`
- `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/hookimpls.py`
- `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/nginx_config.py`
- `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/resources/activity.js.template`
- `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/config_test.py`
- `libs/mngr/imbue/mngr/plugins/user_activity_tracking_via_web/nginx_config_test.py`

**Modified files:**
- `libs/mngr/imbue/mngr/config/data_types.py` - Add PluginsConfig with plugin config
- `libs/mngr/imbue/mngr/plugins/__init__.py` - Register the plugin (if needed)

### Non-Goals (for this phase)

- Host shutdown enforcement based on idle time (separate task)
- `mngr enforce` command (separate task)
- TCP/UDP forwarding (out of scope for this plugin)
- Per-agent activity tracking (host-level is sufficient for now)
