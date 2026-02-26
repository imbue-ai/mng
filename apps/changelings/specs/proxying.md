We need to proxy requests that go to /agents/{agent_id}/ to the appropriate backend agent server, which is running somewhere else (eg on localhost:{port} if it's a local agent, or on some Modal endpoint if it's a remote agent).

The simpler way would be to use sub-domains, but we don't control the DNS or URLs where user's agents are being served, so we have to do it with URL paths instead.

In order to do that, we need to use a combination of service workers, script injection, and rewriting.

There's a rough implementation in proxying.py 

The key pieces:
Routing logic in the proxy endpoint:

/agents/{agent_id}/__sw.js → serves the templated Service Worker
Navigation request + no SW cookie → serves bootstrap HTML
Everything else → strips the prefix, proxies to the backend, injects the WS shim into HTML responses

WebSocket proxying is handled separately since FastAPI has its own @app.websocket decorator. It just opens a bidirectional pipe between the client and the backend, with asyncio.gather running both directions concurrently.
Things you'd want to customize:

get_backend_url() — replace the hardcoded dict with whatever your actual agent→backend mapping is (probably a DB lookup or Modal endpoint resolution)
The shell page dropdown — make it dynamic based on available agents
You might want to add httpx connection pooling / limits for production
The excluded headers set when proxying — you may need to tune this depending on what your backends send (especially around caching headers, Set-Cookie path rewriting, etc.)
