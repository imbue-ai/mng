#!/usr/bin/env bash
# Migrate external state from mng -> mngr naming.
#
# This handles user-local state: directories, env vars, agent data, Claude data, etc.
# Run this AFTER the code migration (migrate_code_mng_to_mngr.sh) and AFTER
# all active Claude Code sessions on this repo are closed (except the one
# running this script).
#
# Usage:
#   scripts/migrate_state_mng_to_mngr.sh [--dry-run] [checkout_dir ...]
#
# Pass one or more additional checkout directories to migrate their .mng/ dirs.
# The script automatically migrates ~/.mng and the project it lives in.

set -euo pipefail

# Auto-detect the repo root this script lives in
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

DRY_RUN=false
EXTRA_DIRS=()
for arg in "$@"; do
    if [ "$arg" = "--dry-run" ]; then
        DRY_RUN=true
    else
        EXTRA_DIRS+=("$arg")
    fi
done

info()  { echo -e "  ${CYAN}>${NC} $*"; }
ok()    { echo -e "  ${GREEN}OK${NC} $*"; }
warn()  { echo -e "  ${YELLOW}!!${NC} $*"; }
err()   { echo -e "  ${RED}ERROR${NC} $*"; }
step()  { echo -e "\n${BOLD}${CYAN}[$1/${TOTAL_STEPS}]${NC} ${BOLD}$2${NC}"; }
skip()  { echo -e "  ${CYAN}skip${NC} $*"; }
dry()   { echo -e "  ${CYAN}[dry-run] $*${NC}"; }

TOTAL_STEPS=9

copy_missing_files() {
    local src="$1"
    local dst="$2"
    # Copy everything from src to dst that doesn't already exist in dst.
    # Uses cp -a to preserve permissions/symlinks and -n to skip existing.
    # macOS cp returns exit code 1 when -n skips files, so we ignore it.
    if [ "$DRY_RUN" = true ]; then
        dry "would copy missing files from $src to $dst"
    else
        cp -a -n "$src"/. "$dst"/ 2>/dev/null || true
    fi
}

migrate_dir() {
    local mng_dir="$1/.mng"
    local mngr_dir="$1/.mngr"
    local label="$2"

    if [ ! -d "$mng_dir" ]; then
        skip "No $label/.mng/ found (already migrated or never existed)."
        return
    fi

    if [ ! -d "$mngr_dir" ]; then
        if [ "$DRY_RUN" = true ]; then
            dry "would rename $label/.mng/ -> $label/.mngr/"
        else
            mv "$mng_dir" "$mngr_dir"
            ok "Renamed $label/.mng/ -> $label/.mngr/"
        fi
        return
    fi

    # Both exist -- copy all missing files from old to new
    copy_missing_files "$mng_dir" "$mngr_dir"

    # Check if they're now identical
    if [ "$DRY_RUN" = true ]; then
        if diff -rq "$mng_dir" "$mngr_dir" > /dev/null 2>&1; then
            dry "would remove $label/.mng/ (identical to .mngr/)"
        else
            dry "$label/.mng/ and $label/.mngr/ differ -- would keep both"
        fi
    else
        if diff -rq "$mng_dir" "$mngr_dir" > /dev/null 2>&1; then
            rm -rf "$mng_dir"
            ok "Removed $label/.mng/ (identical to .mngr/)"
        else
            warn "$label/.mng/ and $label/.mngr/ differ after copying. Keeping both."
            info "Inspect diff: ${CYAN}diff -r $mng_dir $mngr_dir${NC}"
        fi
    fi
}

if [ "$DRY_RUN" = true ]; then
    echo -e "${BOLD}mng -> mngr state migration ${YELLOW}(DRY RUN)${NC}"
else
    echo -e "${BOLD}mng -> mngr state migration${NC}"
fi

# ── 1. Clean build artifacts ─────────────────────────────────────

step 1 "Cleaning build artifacts..."
if [ "$DRY_RUN" = true ]; then
    for pat in __pycache__ htmlcov .pytest_cache .test_output; do
        count=$(find "$REPO_ROOT" -type d -name "$pat" 2>/dev/null | wc -l | tr -d ' ')
        [ "$count" -gt 0 ] && dry "would remove $count $pat directories"
    done
    count=$(find "$REPO_ROOT" -name coverage.xml 2>/dev/null | wc -l | tr -d ' ')
    [ "$count" -gt 0 ] && dry "would remove $count coverage.xml files"
else
    find "$REPO_ROOT" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find "$REPO_ROOT" -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
    find "$REPO_ROOT" -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
    find "$REPO_ROOT" -type d -name .test_output -exec rm -rf {} + 2>/dev/null || true
    find "$REPO_ROOT" -name coverage.xml -delete 2>/dev/null || true
    ok "Cleaned __pycache__, htmlcov, .pytest_cache, .test_output, coverage.xml"
fi

# Remove empty leftover directories from the old mng names
for d in "$REPO_ROOT"/libs/mng "$REPO_ROOT"/libs/mng_*; do
    [ -d "$d" ] || continue
    if find "$d" -type f | read -r; then
        warn "$(basename "$d") is not empty and may need manual cleanup"
    elif [ "$DRY_RUN" = true ]; then
        dry "would remove empty $(basename "$d")"
    else
        rm -rf "$d"
        ok "Removed empty $(basename "$d")"
    fi
done

# ── 2. Remove mng binary ──────────────────────────────────────────

step 2 "Removing mng binary..."
mng_bin=$(command -v mng 2>/dev/null || true)
if [ -n "$mng_bin" ]; then
    if [ "$DRY_RUN" = true ]; then
        dry "would remove $mng_bin"
    else
        rm "$mng_bin"
        ok "Removed $mng_bin"
    fi
else
    ok "No mng binary found in PATH (already removed)."
fi

if uv tool list 2>/dev/null | grep -q '^mng '; then
    if [ "$DRY_RUN" = true ]; then
        dry "would uninstall mng uv tool"
    else
        uv tool uninstall mng
        ok "Uninstalled mng uv tool"
    fi
fi

echo ""

# ── 3. Migrate ~/.mng/ -> ~/.mngr/ ─────────────────────────────────

step 3 "Migrating data directories..."
migrate_dir "$HOME" "~"

# Migrate .mng dirs inside worktrees (these are gitignored local state)
for wt in "$HOME/.mngr/worktrees"/*/; do
    [ -d "$wt/.mng" ] && migrate_dir "${wt%/}" "${wt%/}"
done

# Migrate .mng in the project this script lives in
migrate_dir "$REPO_ROOT" "$REPO_ROOT"

# Also migrate .mng dirs inside worktrees under this checkout
if [ -d "$REPO_ROOT/.mngr/worktrees" ]; then
    for wt in "$REPO_ROOT/.mngr/worktrees"/*/; do
        [ -d "$wt/.mng" ] && migrate_dir "${wt%/}" "${wt%/}"
    done
fi

echo ""

# Migrate any additional checkout dirs passed as arguments
for repo_dir in "${EXTRA_DIRS[@]+"${EXTRA_DIRS[@]}"}"; do
    migrate_dir "$repo_dir" "$repo_dir"

    if [ -d "$repo_dir/.mngr/worktrees" ]; then
        for wt in "$repo_dir/.mngr/worktrees"/*/; do
            [ -d "$wt/.mng" ] && migrate_dir "${wt%/}" "${wt%/}"
        done
    fi

    if [ -f "$repo_dir/.envrc" ] && grep -qi 'mng' "$repo_dir/.envrc" 2>/dev/null; then
        echo ""
        echo -e "${RED}Found 'mng' references in $repo_dir/.envrc:${NC}"
        grep -ni 'mng' "$repo_dir/.envrc" | grep -vi 'mngr' | sed 's/^/  /'
        echo -e "  To fix: ${CYAN}perl -pi -e 's/MNG(?!R)/MNGR/g; s/\\.mng(?!r)/.mngr/g; s/\\/mng(?!r)/\\/mngr/g' $repo_dir/.envrc${NC}"
    fi

    echo ""
done

# ── 4. Check shell configs for stale references ────────────────────

step 4 "Checking shell configs for stale references..."

found_any=false
for rc in "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.zshenv" "$HOME/.config/fish/config.fish" "$HOME/.envrc"; do
    if [ -f "$rc" ] && grep -qi 'mng' "$rc" 2>/dev/null && grep -qiv 'mngr' "$rc" 2>/dev/null; then
        if [ "$found_any" = false ]; then
            found_any=true
        fi
        echo -e "${RED}Found 'mng' references in $rc:${NC}"
        grep -ni 'mng' "$rc" | grep -vi 'mngr' | sed 's/^/  /'
        echo -e "  To fix: ${CYAN}perl -pi -e 's/MNG(?!R)/MNGR/g; s/\\.mng(?!r)/.mngr/g; s/\\/mng(?!r)/\\/mngr/g' $rc${NC}"
        echo ""
    fi
done
if [ "$found_any" = false ]; then
    ok "No stale references found in shell configs."
fi

# ── 5. Check current env vars for stale references ─────────────────

step 5 "Checking environment variables..."

stale_vars=$(env | grep -i '_mng_\|^mng_\|\.mng' | grep -iv 'mngr' || true)
if [ -n "$stale_vars" ]; then
    warn "Found environment variables containing 'mng' (not 'mngr'):"
    echo "$stale_vars" | sed 's/^/  /'
    echo ""
else
    ok "No stale environment variables found."
fi

# ── 6. Fix agent data.json files ────────────────────────────────────

step 6 "Fixing agent data.json files..."

# Agent connect commands have baked-in MNG_ env var names and .mng paths
agent_fixed=0
for f in "$HOME/.mngr/agents"/*/data.json; do
    [ -f "$f" ] || continue
    if grep -qP 'MNG(?!R)_|\.mng(?!r)' "$f" 2>/dev/null; then
        if [ "$DRY_RUN" = true ]; then
            dry "would fix stale references in $f"
        else
            perl -pi -e 's/MNG(?!R)/MNGR/g; s/\.mng(?!r)/.mngr/g' "$f"
        fi
        agent_fixed=$((agent_fixed + 1))
    fi
done
if [ "$agent_fixed" -gt 0 ]; then
    ok "Fixed $agent_fixed agent data.json files (MNG_ env vars and .mng paths)"
else
    ok "No agent data.json files need fixing."
fi

# Host data.json has .mng worktree paths and MNG_ env vars
host_fixed=0
for f in "$HOME/.mngr/data.json" "$HOME/.mngr/hosts"/*/data.json; do
    [ -f "$f" ] || continue
    if grep -qP '\.mng(?!r)|MNG(?!R)_' "$f" 2>/dev/null; then
        if [ "$DRY_RUN" = true ]; then
            dry "would fix stale references in $f"
        else
            perl -pi -e 's/MNG(?!R)/MNGR/g; s/\.mng(?!r)/.mngr/g' "$f"
            ok "Fixed stale references in $f"
        fi
        host_fixed=$((host_fixed + 1))
    fi
done
if [ "$host_fixed" -eq 0 ]; then
    ok "No host data.json files need fixing."
fi

# ── 7. Fix Claude data ─────────────────────────────────────────────

step 7 "Checking Claude data for stale mng references..."

real_hits=0
# ~/.claude.json: contains .mng/ paths as project keys, _mngCreated/_mngSourcePath properties
if [ -f "$HOME/.claude.json" ]; then
    real_hits=$(grep -cE '\.mng|_mngCreated|_mngSourcePath' "$HOME/.claude.json" 2>/dev/null || true)
    if [ "$real_hits" -gt 0 ]; then
        echo -e "${YELLOW}Found ~$real_hits stale 'mng' references in ~/.claude.json${NC}"
        echo -e "  (paths like .mng/, properties like _mngCreated, _mngSourcePath)"
        echo -e "  To fix: ${CYAN}perl -pi -e 's/\\.mng(?!r)/.mngr/g; s/_mngCreated/_mngrCreated/g; s/_mngSourcePath/_mngrSourcePath/g' ~/.claude.json${NC}"
        echo ""
    fi
fi

# ~/.claude/projects/: rename dirs that encode .mng/ paths
renamed_count=0
if [ -d "$HOME/.claude/projects" ]; then
    for dir in "$HOME/.claude/projects"/*mng*; do
        [ -d "$dir" ] || continue
        # Only rename dirs containing mng but not mngr
        case "$(basename "$dir")" in
            *mngr*) continue ;;
        esac
        newdir=$(echo "$dir" | sed 's/--mng-/--mngr-/g; s/\.mng/.mngr/g')
        if [ "$dir" != "$newdir" ] && [ ! -e "$newdir" ]; then
            if [ "$DRY_RUN" = true ]; then
                dry "would rename $(basename "$dir") -> $(basename "$newdir")"
            else
                mv "$dir" "$newdir"
            fi
            renamed_count=$((renamed_count + 1))
        fi
    done
fi
if [ "$renamed_count" -gt 0 ]; then
    ok "Renamed $renamed_count Claude project dirs (.mng -> .mngr)"
fi

if [ "$real_hits" -eq 0 ] && [ "$renamed_count" -eq 0 ]; then
    ok "No stale mng references found in Claude data."
fi

# ── 8. Rename ~/.config/mng ────────────────────────────────────────

step 8 "Renaming ~/.config/mng..."

if [ -d "$HOME/.config/mng" ] && [ ! -d "$HOME/.config/mngr" ]; then
    if [ "$DRY_RUN" = true ]; then
        dry "would rename ~/.config/mng -> ~/.config/mngr"
    else
        mv "$HOME/.config/mng" "$HOME/.config/mngr"
        ok "Renamed ~/.config/mng -> ~/.config/mngr"
    fi
elif [ -d "$HOME/.config/mng" ]; then
    warn "Both ~/.config/mng and ~/.config/mngr exist. Leaving both."
else
    ok "No ~/.config/mng found."
fi

# ── 9. Clean uv cache ──────────────────────────────────────────────

step 9 "Cleaning uv cache..."
if [ "$DRY_RUN" = true ]; then
    dry "would clean uv cache"
else
    uv cache clean 2>/dev/null && ok "uv cache cleaned" || true
fi

echo ""
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}This was a dry run. No changes were made.${NC}"
else
    echo -e "${CYAN}Note: References to the GitHub repo URL will need updating"
    echo -e "separately if/when the repo is renamed.${NC}"
    echo ""
    echo -e "${GREEN}Done.${NC} Run ${BOLD}uv sync --all-packages${NC} in your checkout."
fi
