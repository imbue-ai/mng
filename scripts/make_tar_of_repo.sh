#!/bin/bash

# This script exists to create a tarball of a "keyframe" commit of the current git repository. This keyframe is then
# cached within the Docker or Modal image, which allows us to speed up CI builds by avoiding having to clone the entire
# git history every time.
set -euo pipefail

HASH="$1"
DEST="$2"

mkdir -p "$DEST";


[ -e "$DEST/$HASH.checkpoint" ] || ( \
  tmp=$(mktemp -d); \
  rm -rf "$tmp"; \
  git clone . "$tmp"; \
  git -C "$tmp" checkout "$HASH"; \
  mv "$tmp" "$DEST/$HASH"; \
  COPYFILE_DISABLE=1 tar czf "$DEST/current.tar.gz" -C "$DEST/$HASH" .; \
  rm -rf "$DEST/$HASH"; \
  touch "$DEST/$HASH.checkpoint"; \
)
