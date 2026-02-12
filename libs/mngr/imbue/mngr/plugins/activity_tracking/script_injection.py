from imbue.imbue_common.pure import pure


@pure
def generate_activity_tracking_script(
    api_base_url: str,
    agent_id: str,
    api_token: str,
    debounce_ms: int,
) -> str:
    """Generate the JavaScript snippet that sends activity heartbeats.

    This script is injected into proxied web pages via nginx sub_filter.
    It listens for user interaction events and periodically sends heartbeat
    POSTs to the API server.
    """
    return f"""<script>
(function() {{
  var lastReport = 0;
  var debounce = {debounce_ms};
  var url = '{api_base_url}/api/agents/{agent_id}/activity';
  var token = '{api_token}';

  function report() {{
    var now = Date.now();
    if (now - lastReport < debounce) return;
    lastReport = now;
    fetch(url, {{
      method: 'POST',
      headers: {{'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}},
      body: '{{}}'
    }}).catch(function() {{}});
  }}

  ['keydown', 'mousedown', 'mousemove', 'touchstart', 'scroll'].forEach(function(evt) {{
    document.addEventListener(evt, report, {{passive: true}});
  }});
}})();
</script>"""


@pure
def generate_nginx_sub_filter_config(
    api_base_url: str,
    agent_id: str,
    api_token: str,
    debounce_ms: int,
) -> str:
    """Generate the nginx sub_filter directive for injecting the activity tracking script.

    This should be included in the nginx location block for the proxied service.
    """
    script = generate_activity_tracking_script(
        api_base_url=api_base_url,
        agent_id=agent_id,
        api_token=api_token,
        debounce_ms=debounce_ms,
    )
    # Escape for nginx config (single quotes become escaped)
    escaped_script = script.replace("'", "\\'")
    return f"""sub_filter '</body>' '{escaped_script}</body>';
sub_filter_once on;
sub_filter_types text/html;"""
