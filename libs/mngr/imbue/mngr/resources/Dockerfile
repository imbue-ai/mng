FROM python:3.11-slim

# Install system dependencies including tini for proper signal handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    curl \
    fd-find \
    git \
    git-lfs \
    jq \
    openssh-server \
    ripgrep \
    rsync \
    tini \
    tmux \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
RUN echo 'PATH="/root/.local/bin:$PATH"' >> /root/.bashrc

# Install claude code
RUN curl -fsSL https://claude.ai/install.sh > /tmp/install_claude.sh && ( cat /tmp/install_claude.sh | bash ) || ( cat /tmp/install_claude.sh && exit 1 )
ENV PATH="/root/.claude/local/bin:$PATH"
RUN echo 'PATH="/root/.claude/local/bin:$PATH"' >> /root/.bashrc

# Use tini as init system to handle signals properly
ENTRYPOINT ["/usr/bin/tini", "--"]
