"""
Service Worker-based reverse proxy for multiplexing sub-sites
behind /agents/{agent_id}/ path prefixes.

pip install fastapi uvicorn httpx websockets
"""

import asyncio
import re

import httpx
from fastapi import FastAPI
from fastapi import Request
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.responses import Response

app = FastAPI()

# ---------------------------------------------------------------------------
# Configuration: map agent IDs to their backend URLs
# ---------------------------------------------------------------------------


def get_backend_url(agent_id: str) -> str | None:
    """
    Return the backend base URL for a given agent_id.
    Replace this with your actual lookup logic (DB, config, etc.)
    """
    backends = {
        "site-a": "http://localhost:3001",
        "site-b": "http://localhost:3002",
        "site-c": "http://localhost:3003",
    }
    return backends.get(agent_id)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def bootstrap_html(agent_id: str) -> str:
    prefix = f"/agents/{agent_id}"
    return f"""<!DOCTYPE html>
<html><head><title>Loading...</title></head>
<body>
<p>Loading...</p>
<script>
const PREFIX = '{prefix}/';
const SW_URL = PREFIX + '__sw.js';

async function boot() {{
  const reg = await navigator.serviceWorker.register(SW_URL, {{ scope: PREFIX }});
  const sw = reg.installing || reg.waiting || reg.active;

  function onActivated() {{
    document.cookie = 'sw_installed_{agent_id}=1; path=' + PREFIX;
    location.reload();
  }}

  if (sw.state === 'activated') {{
    onActivated();
    return;
  }}

  sw.addEventListener('statechange', () => {{
    if (sw.state === 'activated') onActivated();
  }});
}}

boot().catch(err => {{
  document.body.textContent = 'Failed to initialize: ' + err.message;
}});
</script>
</body></html>"""


def service_worker_js(agent_id: str) -> str:
    prefix = f"/agents/{agent_id}"
    return f"""
const PREFIX = '{prefix}';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {{
  const url = new URL(event.request.url);

  // Only rewrite same-origin requests
  if (url.origin !== location.origin) return;

  // Already prefixed — let it through
  if (url.pathname.startsWith(PREFIX + '/') || url.pathname === PREFIX) return;

  // Skip the SW script itself
  if (url.pathname.endsWith('__sw.js')) return;

  // Rewrite: /foo → /agents/site-a/foo
  url.pathname = PREFIX + url.pathname;

  const init = {{
    method: event.request.method,
    headers: event.request.headers,
    mode: event.request.mode,
    credentials: event.request.credentials,
    redirect: 'manual',
  }};

  // Only attach body for methods that support it
  if (!['GET', 'HEAD'].includes(event.request.method)) {{
    init.body = event.request.body;
    init.duplex = 'half';
  }}

  event.respondWith(fetch(new Request(url.toString(), init)));
}});
"""


def websocket_shim_js(agent_id: str) -> str:
    prefix = f"/agents/{agent_id}"
    return f"""<script>
(function() {{
  var PREFIX = '{prefix}';
  var OrigWebSocket = window.WebSocket;

  window.WebSocket = function(url, protocols) {{
    try {{
      var parsed = new URL(url, location.origin);
      if (parsed.host === location.host) {{
        if (!parsed.pathname.startsWith(PREFIX + '/') && parsed.pathname !== PREFIX) {{
          parsed.pathname = PREFIX + parsed.pathname;
        }}
        url = parsed.toString();
      }}
    }} catch(e) {{}}
    return protocols !== undefined
      ? new OrigWebSocket(url, protocols)
      : new OrigWebSocket(url);
  }};

  window.WebSocket.prototype = OrigWebSocket.prototype;
  window.WebSocket.CONNECTING = OrigWebSocket.CONNECTING;
  window.WebSocket.OPEN = OrigWebSocket.OPEN;
  window.WebSocket.CLOSING = OrigWebSocket.CLOSING;
  window.WebSocket.CLOSED = OrigWebSocket.CLOSED;
}})();
</script>"""


def shell_page_html() -> str:
    return """<!DOCTYPE html>
<html>
<head>
  <title>Agent Gateway</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { display: flex; flex-direction: column; height: 100vh; font-family: system-ui; }
    nav {
      padding: 8px 16px;
      background: #1a1a2e;
      color: white;
      display: flex;
      align-items: center;
      gap: 12px;
      flex-shrink: 0;
    }
    nav label { font-size: 14px; }
    select { padding: 4px 8px; border-radius: 4px; font-size: 14px; }
    iframe { flex: 1; border: none; width: 100%; }
  </style>
</head>
<body>
  <nav>
    <label for="agent-select">Agent:</label>
    <select id="agent-select">
      <option value="site-a">Site A</option>
      <option value="site-b">Site B</option>
      <option value="site-c">Site C</option>
    </select>
  </nav>
  <iframe id="agent-frame" src="/agents/site-a/"></iframe>
  <script>
    document.getElementById('agent-select').addEventListener('change', (e) => {
      document.getElementById('agent-frame').src = '/agents/' + e.target.value + '/';
    });
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------

http_client = httpx.AsyncClient(follow_redirects=False, timeout=30.0)


# ---------------------------------------------------------------------------
# Cookie path rewriting
# ---------------------------------------------------------------------------


def _rewrite_cookie_path(set_cookie: str, agent_id: str) -> str:
    """
    Rewrite the Path attribute in a Set-Cookie header so that cookies
    are scoped under /agents/{agent_id}/ instead of /.

    Examples:
      "sid=abc; Path=/"          → "sid=abc; Path=/agents/site-a/"
      "sid=abc; Path=/api"       → "sid=abc; Path=/agents/site-a/api"
      "sid=abc" (no Path)        → "sid=abc; Path=/agents/site-a/"
    """
    prefix = f"/agents/{agent_id}"

    # Match an existing Path attribute (case-insensitive)
    path_re = re.compile(r"(;\s*[Pp]ath\s*=\s*)([^;]*)")
    m = path_re.search(set_cookie)

    if m:
        original_path = m.group(2).strip()
        # Don't double-prefix if already correct
        if original_path.startswith(prefix):
            return set_cookie
        new_path = prefix + ("" if original_path.startswith("/") else "/") + original_path
        return set_cookie[: m.start(2)] + new_path + set_cookie[m.end(2) :]
    else:
        # No Path attribute — add one scoped to this agent
        return set_cookie + f"; Path={prefix}/"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return HTMLResponse(shell_page_html())


@app.api_route(
    "/agents/{agent_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy(agent_id: str, path: str, request: Request):
    # Serve the service worker script
    if path == "__sw.js":
        return Response(
            content=service_worker_js(agent_id),
            media_type="application/javascript",
        )

    backend = get_backend_url(agent_id)
    if not backend:
        return Response(status_code=404, content=f"Unknown agent: {agent_id}")

    # Check if SW is installed via cookie
    sw_cookie = request.cookies.get(f"sw_installed_{agent_id}")
    is_navigation = request.headers.get("sec-fetch-mode") == "navigate"

    # First HTML navigation without SW → serve bootstrap
    if is_navigation and not sw_cookie:
        return HTMLResponse(bootstrap_html(agent_id))

    # Proxy the request
    proxy_url = f"{backend}/{path}"
    if request.url.query:
        proxy_url += f"?{request.url.query}"

    # Forward headers, dropping host (httpx sets it from the URL)
    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()

    resp = await http_client.request(
        method=request.method,
        url=proxy_url,
        headers=headers,
        content=body,
    )

    # Build response headers, dropping hop-by-hop headers
    excluded = {"transfer-encoding", "content-encoding", "content-length"}
    resp_headers = {}
    for k, v in resp.headers.multi_items():
        if k.lower() in excluded:
            continue
        # Rewrite Set-Cookie paths so cookies are scoped to this agent
        if k.lower() == "set-cookie":
            v = _rewrite_cookie_path(v, agent_id)
        resp_headers.setdefault(k, [])
        resp_headers[k].append(v)

    content = resp.content

    # Inject WebSocket shim into HTML responses
    ct = resp.headers.get("content-type", "")
    if "text/html" in ct:
        html = resp.text
        shim = websocket_shim_js(agent_id)
        if "<head>" in html:
            html = html.replace("<head>", "<head>" + shim, 1)
        elif "<head " in html:
            # Handle <head with attributes>
            idx = html.index("<head ")
            close = html.index(">", idx)
            html = html[: close + 1] + shim + html[close + 1 :]
        else:
            html = shim + html
        content = html.encode()

    response = Response(
        content=content,
        status_code=resp.status_code,
    )
    # Set headers manually to support multiple values (e.g. multiple Set-Cookie)
    for k, vals in resp_headers.items():
        for v in vals:
            response.headers.append(k, v)
    return response


# ---------------------------------------------------------------------------
# WebSocket proxying
# ---------------------------------------------------------------------------


@app.websocket("/agents/{agent_id}/{path:path}")
async def proxy_websocket(websocket: WebSocket, agent_id: str, path: str):
    backend = get_backend_url(agent_id)
    if not backend:
        await websocket.close(code=4004, reason=f"Unknown agent: {agent_id}")
        return

    # Convert http(s) to ws(s)
    ws_backend = backend.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_backend}/{path}"
    if websocket.url.query:
        ws_url += f"?{websocket.url.query}"

    await websocket.accept()

    # Connect to the backend WebSocket
    import websockets

    try:
        async with websockets.connect(ws_url) as backend_ws:

            async def client_to_backend():
                try:
                    while True:
                        data = await websocket.receive()
                        if "text" in data:
                            await backend_ws.send(data["text"])
                        elif "bytes" in data:
                            await backend_ws.send(data["bytes"])
                except WebSocketDisconnect:
                    await backend_ws.close()

            async def backend_to_client():
                try:
                    async for msg in backend_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except Exception:
                    await websocket.close()

            await asyncio.gather(client_to_backend(), backend_to_client())

    except Exception as e:
        try:
            await websocket.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
