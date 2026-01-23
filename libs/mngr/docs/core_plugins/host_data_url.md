# host_data_url Plugin

The `host_data_url` plugin provides a way to access host-specific data via a URL.

In particular, it exposes all file in the host's state directory, and provides additional endpoints for treating logs and events as streams.

Host events and logs *only* include those that happen while the host is online! For logs and events about host creation and destruction, see each individual provider's documentation.

**Note**: because this data is served from within the host, it is only accessible when the host is running.

## TODO

This plugin is not yet implemented. Required features:

- [ ] HTTP server for serving host data via URL
- [ ] Endpoint to expose all files in host's state directory
- [ ] Endpoint for streaming host logs (while host is online)
- [ ] Endpoint for streaming host events (while host is online)
- [ ] Plugin registration using `@hookimpl` decorator
- [ ] Entry point configuration in `pyproject.toml`
