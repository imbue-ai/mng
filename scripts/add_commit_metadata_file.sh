#!/usr/bin/env bash
#
# add_commit_metadata_file.sh
#
# Stores a metadata file (e.g., transcript, HTML report) associated with the current
# git commit, using Git LFS on an orphan branch. The branch is never checked out
# to avoid slowdown from accumulated files.
#
# Usage: ./add_commit_metadata_file.sh <file_path> <file_type>
#
# Example: ./add_commit_metadata_file.sh output.html transcript
#
# Output: Prints the raw GitHub URL where the file can be accessed.

set -euo pipefail

# Configuration
BRANCH_NAME="${COMMIT_METADATA_BRANCH:-commit-metadata}"
MAX_PUSH_RETRIES=3

# Colors for output (disabled if not a terminal)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

log_error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
}

log_warn() {
    echo -e "${YELLOW}WARN: $1${NC}" >&2
}

log_info() {
    echo -e "${GREEN}$1${NC}" >&2
}

cleanup() {
    if [[ -n "${GIT_INDEX_FILE:-}" && -f "$GIT_INDEX_FILE" ]]; then
        rm -f "$GIT_INDEX_FILE"
    fi
}

trap cleanup EXIT

# Validate inputs
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <file_path> <file_type>" >&2
    echo "Example: $0 output.html transcript" >&2
    exit 1
fi

FILE_PATH="$1"
FILE_TYPE="$2"

if [[ ! -f "$FILE_PATH" ]]; then
    log_error "File not found: $FILE_PATH"
    exit 1
fi

if [[ -z "$FILE_TYPE" ]]; then
    log_error "File type cannot be empty"
    exit 1
fi

# Validate file type (alphanumeric, hyphens, underscores, forward slashes only)
if [[ ! "$FILE_TYPE" =~ ^[a-zA-Z0-9_/-]+$ ]]; then
    log_error "File type must be alphanumeric (hyphens, underscores, and forward slashes allowed): $FILE_TYPE"
    exit 1
fi

# Check we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    log_error "Not in a git repository"
    exit 1
fi

# Check git-lfs is installed
if ! command -v git-lfs &> /dev/null; then
    log_error "git-lfs is not installed. Please install it first."
    exit 1
fi

# Check remote exists
if ! git remote get-url origin > /dev/null 2>&1; then
    log_error "No 'origin' remote configured"
    exit 1
fi

# Gather context
COMMIT_SHA=$(git rev-parse HEAD)
FILE_EXT="${FILE_PATH##*.}"
SHARD="${COMMIT_SHA:0:2}"
DEST_PATH="${SHARD}/${COMMIT_SHA}/${FILE_TYPE}.${FILE_EXT}"

log_info "Storing $FILE_TYPE for commit $COMMIT_SHA"

# Create LFS pointer and store content locally
# git lfs clean reads from stdin and outputs the pointer, storing actual content in .git/lfs/objects/
POINTER_CONTENT=$(cat "$FILE_PATH" | git lfs clean "$DEST_PATH")

if [[ -z "$POINTER_CONTENT" ]]; then
    log_error "Failed to create LFS pointer"
    exit 1
fi

# Extract OID from pointer for later push
# Pointer format:
# version https://git-lfs.github.com/spec/v1
# oid sha256:abc123...
# size 12345
OID=$(echo "$POINTER_CONTENT" | grep "^oid sha256:" | cut -d: -f2)

if [[ -z "$OID" ]]; then
    log_error "Failed to extract OID from LFS pointer"
    exit 1
fi

# Create blob from pointer content
BLOB_SHA=$(echo "$POINTER_CONTENT" | git hash-object -w --stdin)

# Set up temporary index file (critical: avoids touching working directory)
export GIT_INDEX_FILE=$(mktemp)

# Function to create commit on the metadata branch
create_commit() {
    local parent_ref="$1"

    # Clear the temp index by reading an empty tree
    # (touch creates an invalid index; we need a proper empty one)
    git read-tree --empty

    # Read existing tree if we have a parent
    if [[ -n "$parent_ref" ]]; then
        git read-tree "$parent_ref"
    fi

    # Add our file to the index
    git update-index --add --cacheinfo "100644,$BLOB_SHA,$DEST_PATH"

    # Write the tree
    local tree_sha
    tree_sha=$(git write-tree)

    # Create commit
    local commit_msg="Add $FILE_TYPE for commit $COMMIT_SHA"
    local new_commit
    if [[ -n "$parent_ref" ]]; then
        new_commit=$(echo "$commit_msg" | git commit-tree "$tree_sha" -p "$parent_ref")
    else
        new_commit=$(echo "$commit_msg" | git commit-tree "$tree_sha")
    fi

    echo "$new_commit"
}

# Check if branch exists locally or on remote
BRANCH_EXISTS_LOCAL=false
BRANCH_EXISTS_REMOTE=false
PARENT_REF=""

if git rev-parse --verify "refs/heads/$BRANCH_NAME" > /dev/null 2>&1; then
    BRANCH_EXISTS_LOCAL=true
    PARENT_REF="refs/heads/$BRANCH_NAME"
fi

# Fetch remote branch info
git fetch origin "$BRANCH_NAME" 2>/dev/null || true

if git rev-parse --verify "refs/remotes/origin/$BRANCH_NAME" > /dev/null 2>&1; then
    BRANCH_EXISTS_REMOTE=true
    # If remote is ahead of local (or local doesn't exist), use remote as parent
    if [[ "$BRANCH_EXISTS_LOCAL" == false ]]; then
        PARENT_REF="refs/remotes/origin/$BRANCH_NAME"
    else
        # Check if remote is ahead
        local_sha=$(git rev-parse "refs/heads/$BRANCH_NAME")
        remote_sha=$(git rev-parse "refs/remotes/origin/$BRANCH_NAME")
        if [[ "$local_sha" != "$remote_sha" ]]; then
            # Check if remote contains local (local is behind)
            if git merge-base --is-ancestor "$local_sha" "$remote_sha" 2>/dev/null; then
                PARENT_REF="refs/remotes/origin/$BRANCH_NAME"
            fi
        fi
    fi
fi

# Create the commit
NEW_COMMIT=$(create_commit "$PARENT_REF")

# Update local branch ref
git update-ref "refs/heads/$BRANCH_NAME" "$NEW_COMMIT"

log_info "Created commit $NEW_COMMIT"

# Push LFS objects first
log_info "Pushing LFS objects..."
git lfs push origin --object-id "$OID"

# Push branch with retry logic for race conditions
push_succeeded=false
for ((i=1; i<=MAX_PUSH_RETRIES; i++)); do
    if git push origin "$BRANCH_NAME" 2>/dev/null; then
        push_succeeded=true
        break
    fi

    if [[ $i -lt $MAX_PUSH_RETRIES ]]; then
        log_warn "Push failed (attempt $i/$MAX_PUSH_RETRIES), fetching and retrying..."

        # Fetch latest
        git fetch origin "$BRANCH_NAME"

        # Recreate commit with remote as parent
        NEW_COMMIT=$(create_commit "refs/remotes/origin/$BRANCH_NAME")
        git update-ref "refs/heads/$BRANCH_NAME" "$NEW_COMMIT"

        log_info "Recreated commit $NEW_COMMIT"
    fi
done

if [[ "$push_succeeded" == false ]]; then
    log_error "Failed to push after $MAX_PUSH_RETRIES attempts"
    exit 1
fi

log_info "Push succeeded"

# Determine repo owner/name from remote URL
REMOTE_URL=$(git remote get-url origin)

# Handle both HTTPS and SSH URLs
# HTTPS: https://github.com/owner/repo.git
# SSH: git@github.com:owner/repo.git
if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
else
    log_warn "Could not parse GitHub owner/repo from remote URL: $REMOTE_URL"
    log_warn "Outputting partial URL"
    OWNER="OWNER"
    REPO="REPO"
fi

# Output the URLs
RAW_URL="https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH_NAME}/${DEST_PATH}"
WEB_URL="https://github.com/${OWNER}/${REPO}/blob/${BRANCH_NAME}/${DEST_PATH}"
echo ""
echo "File stored successfully!"
echo ""
echo "GitHub Web UI (works when logged in):"
echo "  $WEB_URL"
echo ""
echo "Raw URL (public repos, or use with token for private):"
echo "  $RAW_URL"
