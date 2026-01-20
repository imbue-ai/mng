# User Activity Tracking via Web Spec

This plugin tracks user activity in web interfaces to prevent hosts from idling while the user is active.

See [user-facing documentation](../../docs/core_plugins/user_activity_tracking_via_web.md) for usage.

## Problem

When a user interacts with an agent via web interface (e.g., ttyd terminal), the host's idle detection system needs to know the user is active.
Without this, hosts may auto-stop while the user is reading output or thinking.

## Solution

Inject JavaScript into all HTML responses that:
1. Listens for user input events
2. Reports activity to an nginx endpoint
3. Endpoint injects content to the activity file

## JavaScript Injection

nginx uses `ngx_http_sub_module` to inject a `<script>` tag into HTML responses.

### activity.js

Location: `/etc/mngr/nginx/plugins.d/user_activity_tracking_via_web/activity.js`

```javascript
(function() {
  var debounceMs = 1000;
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

  // Keyboard events
  document.addEventListener('keydown', report, true);
  document.addEventListener('keypress', report, true);

  // Mouse events
  document.addEventListener('mousemove', report, true);
  document.addEventListener('click', report, true);
  document.addEventListener('scroll', report, true);
})();
```

The script:
- Uses an IIFE to avoid polluting global namespace
- Debounces reports to at most once per `debounceMs` (configurable, default 1000ms)
- Captures events in capture phase (`true` third argument) to catch events before any page handlers
- Sends fire-and-forget POST requests (ignores response)

## Nginx Configuration

Location: `/etc/mngr/nginx/plugins.d/user_activity_tracking_via_web.conf`

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

# Handle activity reports
location = /_mngr/plugin/user_activity_tracking_via_web/activity {
    content_by_lua_block {
        os.execute("echo user_activity > " .. os.getenv("MNGR_HOST_DIR") .. "/activity/user")
        ngx.status = 204
        ngx.exit(ngx.HTTP_NO_CONTENT)
    }
}
```

### Alternative without lua

If nginx doesn't have lua support, use FastCGI:

```nginx
location = /_mngr/plugin/user_activity_tracking_via_web/activity {
    fastcgi_pass unix:/var/run/mngr-activity.sock;
    include fastcgi_params;
}
```

With a simple FastCGI handler that just sticks some placeholder content in the file.

## Activity File

Path: `$MNGR_HOST_DIR/activity/user`

This is the same file used by `mngr connect` for terminal activity tracking. mngr checks the modification time of this file to determine user activity.

See [idle_detection spec](../idle_detection.md) for how this integrates with host lifecycle.

## Configuration

Stored in mngr config, passed to nginx via environment or generated config:

| Setting | Default | Description |
|---------|---------|-------------|
| `debounce_ms` | 1000 | Minimum ms between activity reports |

```toml
[plugins.user_activity_tracking_via_web]
debounce_ms = 1000
```

The debounce value is embedded in the generated `activity.js` file.

## Lifecycle

## Privacy

Only the file modification time is recorded. The plugin does not:
- Log actual keystrokes
- Record mouse positions
- Store any event data
- Send any data outside the host

The sole purpose is answering "when was the user last active?"

## Dependencies

Requires nginx to be running, typically provided by [local_port_forwarding_via_frp_and_nginx](./local_port_forwarding_via_frp_and_nginx.md).

nginx requirements:
- `ngx_http_sub_module` - For HTML injection (included in most nginx builds)
- `ngx_http_lua_module` OR FastCGI - For handling activity endpoint
