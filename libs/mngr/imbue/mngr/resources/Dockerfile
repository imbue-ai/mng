FROM python:3.11-slim

# Install system dependencies including tini for proper signal handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    curl \
    openssh-server \
    tmux \
    build-essential \
    ripgrep \
    fd-find \
    jq \
    rsync \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install claude code
RUN curl -fsSL https://claude.ai/install.sh | sh
ENV PATH="/root/.claude/local/bin:$PATH"

# Use tini as init system to handle signals properly
ENTRYPOINT ["/usr/bin/tini", "--"]
