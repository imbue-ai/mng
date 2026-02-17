#!/usr/bin/env bash
#
# mngr installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/imbue-ai/mngr/main/scripts/install.sh | bash
# [TODO] Replace with vanity URL: curl -fsSL https://imbue.com/mngr/install.sh | bash
#
# This script:
#   1. Installs system dependencies (git, tmux, jq, curl, rsync, unison)
#   2. Installs uv (if not already installed)
#   3. Installs mngr via uv tool install
#
set -euo pipefail

BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

info() {
    printf "${BOLD}==> %s${RESET}\n" "$1"
}

warn() {
    printf "${BOLD}WARNING: %s${RESET}\n" "$1" >&2
}

error() {
    printf "${BOLD}ERROR: %s${RESET}\n" "$1" >&2
    exit 1
}

# ── Detect OS ──────────────────────────────────────────────────────────────────

detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)  echo "linux" ;;
        *)      error "Unsupported operating system: $(uname -s). mngr supports macOS and Linux." ;;
    esac
}

OS="$(detect_os)"

# ── Install system dependencies ────────────────────────────────────────────────

SYSTEM_DEPS=(git tmux jq curl rsync unison)

missing=()
for dep in "${SYSTEM_DEPS[@]}"; do
    if ! command -v "$dep" &>/dev/null; then
        missing+=("$dep")
    fi
done

info "Detected OS: ${OS}"

if [ ${#missing[@]} -eq 0 ]; then
    info "All system dependencies already installed"
elif [ "$OS" = "macos" ]; then
    if ! command -v brew &>/dev/null; then
        error "Missing dependencies: ${missing[*]}. Install them manually, or install Homebrew (https://brew.sh) and re-run this script."
    fi
    info "Installing system dependencies: ${missing[*]}"
    brew install "${missing[@]}"
elif [ "$OS" = "linux" ]; then
    if ! command -v apt-get &>/dev/null; then
        error "apt-get not found. On non-Debian systems, manually install: ${missing[*]}"
    fi
    info "Installing system dependencies: ${missing[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${missing[@]}"
fi

# ── Install uv ─────────────────────────────────────────────────────────────────

if command -v uv &>/dev/null; then
    info "uv is already installed ($(uv --version))"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # The uv installer creates an env file that adds its bin dir to PATH.
    # Source it so uv is available in this script without restarting the shell.
    [ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"

    if ! command -v uv &>/dev/null; then
        error "uv was installed but is not on PATH. Restart your shell and run this script again."
    fi

    info "uv installed ($(uv --version))"
fi

# ── Install mngr ──────────────────────────────────────────────────────────────

info "Installing mngr..."
uv tool install mngr

info "Verifying installation..."
if command -v mngr &>/dev/null; then
    mngr --version 2>/dev/null || true
    info "mngr installed successfully"
else
    warn "mngr was installed but is not on PATH."
    warn "You may need to add ~/.local/bin to your PATH:"
    printf '  export PATH="$HOME/.local/bin:$PATH"\n'
fi

# ── Next steps ─────────────────────────────────────────────────────────────────

printf "\n"
info "Next steps:"
printf "\n"
printf "  1. Set up Modal (for remote agents):\n"
printf "     ${DIM}uv tool install modal${RESET}\n"
printf "     ${DIM}modal token set${RESET}\n"
printf "\n"
printf "  2. Install Claude Code (for the claude agent type):\n"
printf "     ${DIM}npm install -g @anthropic-ai/claude-code${RESET}\n"
printf "\n"
if [ "$OS" = "macos" ]; then
printf "  3. Enable shell completion (zsh):\n"
printf "     ${DIM}echo 'eval \"\$(_MNGR_COMPLETE=zsh_source mngr)\"' >> ~/.zshrc${RESET}\n"
else
printf "  3. Enable shell completion (bash):\n"
printf "     ${DIM}echo 'eval \"\$(_MNGR_COMPLETE=bash_source mngr)\"' >> ~/.bashrc${RESET}\n"
fi
printf "\n"
printf "  4. Get started:\n"
printf "     ${DIM}mngr --help${RESET}\n"
printf "\n"
