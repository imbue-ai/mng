# mng-opencode

A plugin for [mng](https://github.com/imbue-ai/mng) that registers the [OpenCode](https://github.com/sst/opencode) agent type, allowing you to create and manage OpenCode agents through mng.

## Usage

```bash
# Create an OpenCode agent
mng create my-agent opencode

# Create with additional CLI arguments
mng create my-agent opencode -- --flag value
```

## Installation

`mng-opencode` is installed as part of the mng monorepo:

```bash
uv sync --all-packages
```

The plugin registers itself automatically via setuptools entry points.
