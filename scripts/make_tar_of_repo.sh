#!/bin/bash
set -euo pipefail

HASH="$1"
DEST="$2"

mkdir -p "$DEST";

[ -e "$DEST/$HASH.tar.gz" ] || ( \
  tmp=$(mktemp -d); \
  rm -rf "$tmp"; \
  git clone . "$tmp"; \
  git -C "$tmp" checkout "$HASH"; \
  mv "$tmp" "$DEST/$HASH"; \
  tar czf "$DEST/current.tar.gz" -C "$DEST/$HASH" .; \
  rm -rf "$DEST/$HASH"; \
  touch "$DEST/$HASH.tar.gz"; \
)
