#!/usr/bin/env bash
#
# mngr installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/imbue-ai/mngr/main/scripts/install.sh | bash
#
# This script:
#   1. Checks for prerequisites (curl, ssh)
#   2. Prompts to install system dependencies (git, tmux, jq, rsync, unison)
#   3. Installs uv (if not already installed)
#   4. Installs mngr via uv tool install
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

# ── Check prerequisites ───────────────────────────────────────────────────────

for prereq in curl ssh; do
    if ! command -v "$prereq" &>/dev/null; then
        error "$prereq is required but not found. Please install it and re-run this script."
    fi
done

# ── Install system dependencies ────────────────────────────────────────────────

CORE_DEPS=(git tmux jq)
OPTIONAL_DEPS=(rsync unison)
ALL_DEPS=("${CORE_DEPS[@]}" "${OPTIONAL_DEPS[@]}")

find_missing() {
    local deps=("$@")
    local missing=()
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &>/dev/null; then
            missing+=("$dep")
        fi
    done
    echo "${missing[*]}"
}

install_deps() {
    local deps=("$@")
    if [ ${#deps[@]} -eq 0 ]; then
        return
    fi
    if [ "$OS" = "macos" ]; then
        if ! command -v brew &>/dev/null; then
            error "Missing dependencies: ${deps[*]}. Install them manually, or install Homebrew (https://brew.sh) and re-run this script."
        fi
        info "Installing system dependencies: ${deps[*]}"
        brew install "${deps[@]}"
    elif [ "$OS" = "linux" ]; then
        if ! command -v apt-get &>/dev/null; then
            error "apt-get not found. On non-Debian systems, manually install: ${deps[*]}"
        fi
        info "Installing system dependencies: ${deps[*]}"
        sudo apt-get update -qq
        sudo apt-get install -y -qq "${deps[@]}"
    fi
}

info "Detected OS: ${OS}"

# shellcheck disable=SC2207
missing_all=($(find_missing "${ALL_DEPS[@]}"))

if [ ${#missing_all[@]} -eq 0 ]; then
    info "All system dependencies already installed"
else
    printf "\n"
    printf "mngr needs these system dependencies: ${BOLD}${missing_all[*]}${RESET}\n"
    printf "  rsync and unison are optional (needed for push/pull/pair).\n"
    printf "\n"
    printf "  [a] Install all (%s)\n" "${missing_all[*]}"
    # shellcheck disable=SC2207
    missing_core=($(find_missing "${CORE_DEPS[@]}"))
    if [ ${#missing_core[@]} -gt 0 ]; then
        printf "  [c] Install core only (%s)\n" "${missing_core[*]}"
    fi
    printf "  [n] Skip -- I'll install them myself\n"
    printf "\n"
    printf "Choice [a/c/n]: "
    # Read from /dev/tty since stdin may be piped
    read -r choice < /dev/tty

    case "$choice" in
        a|A|y|Y|"")
            install_deps "${missing_all[@]}"
            ;;
        c|C)
            if [ ${#missing_core[@]} -gt 0 ]; then
                install_deps "${missing_core[@]}"
            else
                info "Core dependencies already installed"
            fi
            ;;
        n|N)
            info "Skipping system dependency installation"
            ;;
        *)
            info "Skipping system dependency installation"
            ;;
    esac
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
printf "  1. Install Claude Code (for the claude agent type):\n"
printf "     ${DIM}npm install -g @anthropic-ai/claude-code${RESET}\n"
printf "\n"
if [ "$OS" = "macos" ]; then
printf "  2. Enable shell completion (zsh):\n"
printf "     ${DIM}echo 'eval \"\$(_MNGR_COMPLETE=zsh_source mngr)\"' >> ~/.zshrc${RESET}\n"
else
printf "  2. Enable shell completion (bash):\n"
printf "     ${DIM}echo 'eval \"\$(_MNGR_COMPLETE=bash_source mngr)\"' >> ~/.bashrc${RESET}\n"
fi
printf "\n"
printf "  3. Get started:\n"
printf "     ${DIM}mngr --help${RESET}\n"
printf "\n"
