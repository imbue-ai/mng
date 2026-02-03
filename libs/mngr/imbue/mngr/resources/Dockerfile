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
    nano \
    openssh-server \
    ripgrep \
    rsync \
    tini \
    tmux \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && echo 'PATH="/root/.local/bin:$PATH"' >> /root/.bashrc
ENV PATH="/root/.local/bin:$PATH"

# Install claude code
RUN curl -fsSL https://claude.ai/install.sh > /tmp/install_claude.sh && ( cat /tmp/install_claude.sh | bash && echo 'PATH="/root/.claude/local/bin:$PATH"' >> /root/.bashrc ) || ( cat /tmp/install_claude.sh && exit 1 )
ENV PATH="/root/.claude/local/bin:$PATH"

# without this, there are some annoying bugs on modal's side with snapshotting
ENV UV_LINK_MODE=copy

# copy in all of our code:
COPY . /code/mngr/

# set working directory
WORKDIR /code/mngr/

# extract our code if we're running from Docker. Modal builds will not have the tar.
RUN if [ -f /code/current.tar.gz ]; then \
       tar -xzf /code/current.tar.gz -C /code/mngr/ && rm /code/*.tar.gz; \
     fi && \
     git config --global --add safe.directory /code/mngr/ && \
     chown -R root:root /code/mngr/

# Delete the .venv file if we accidentally picked it up from the host system
RUN rm -rf /code/mngr/.venv

# install python dependencies
RUN unset UV_INDEX_URL && uv sync --all-packages

# Run idly forever while being responsive to SIGTERM.
# PID 1 must explicitly install signal handlers in order to respect signals.
# `tail -f /dev/null` does not do this.
# Since `docker stop` issues a `SIGTERM`, we use an explicit `trap`.
# In practice, this appears to enable rapid interactions using `docker stop`.
CMD ["sh", "-c", "trap 'exit 0' TERM; tail -f /dev/null & wait"]
