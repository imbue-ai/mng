#!/usr/bin/env bash

# This script exists to create a tarball of a "keyframe" commit of the current git repository. This keyframe is then
# cached within the Docker or Modal image, which allows us to speed up CI builds by avoiding having to clone the entire
# git history every time.
set -euo pipefail

HASH="$1"
DEST="$2"

mkdir -p "$DEST";

# Validate cached tarball if checkpoint exists; invalidate if corrupted
if [ -e "$DEST/$HASH.checkpoint" ] && [ -e "$DEST/current.tar.gz" ]; then
  if gzip -t "$DEST/current.tar.gz" 2>/dev/null; then
    exit 0
  fi
  echo "Cached tarball is corrupted, recreating..." >&2
  rm -f "$DEST/$HASH.checkpoint" "$DEST/current.tar.gz"
  rm -rf "$DEST/$HASH"
fi

[ -e "$DEST/$HASH.checkpoint" ] || ( \
  tmp=$(mktemp -d); \
  rm -rf "$tmp"; \
  real_origin="https://github.com/$(git remote get-url origin | sed 's|.*github.com[:/]||')"; \
  git clone . "$tmp"; \
  git -C "$tmp" remote set-url origin "$real_origin"; \
  git -C "$tmp" checkout "$HASH"; \
  mv "$tmp" "$DEST/$HASH"; \
  COPYFILE_DISABLE=1 tar czf "$DEST/current.tar.gz" -C "$DEST/$HASH" .; \
  gzip -t "$DEST/current.tar.gz"; \
  rm -rf "$DEST/$HASH"; \
  touch "$DEST/$HASH.checkpoint"; \
)
