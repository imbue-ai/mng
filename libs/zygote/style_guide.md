# Zygote Style Guide

This file documents style guide deltas for the zygote library. These override the root style_guide.md.

## Async/Await

The root style guide says "Never use async or asyncio." This rule is overridden for the zygote library.

Zygote uses async/await throughout because the Anthropic API client is async and the agent loop benefits from non-blocking tool execution. All agent methods, tool executor methods, inner dialog functions, and chat response functions are async.
