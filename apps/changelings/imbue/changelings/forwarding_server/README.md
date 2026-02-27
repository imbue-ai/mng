We need to proxy requests that go to /agents/{agent_id}/ to the appropriate backend agent server, which is running somewhere else (eg on localhost:{port} if it's a local agent, or on some Modal endpoint if it's a remote agent).

The simplest way would be to use sub-domains, but we don't control the DNS or URLs where user's agents are being served, so we have to do it with URL paths instead.

In order to do that, we use a combination of service workers, script injection, and rewriting.
