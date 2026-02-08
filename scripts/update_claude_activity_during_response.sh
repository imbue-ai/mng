#!/bin/bash
# Called by a hook when we start a response, to update the activity timestamp for the claude agent as long as it is replying
# While the file exists, we should continually update the activity timestamp for the claude agent, so that it doesn't get marked as inactive and killed while it's still replying
# When the .claude/active file no longer exists, this script should exit

set -euo pipefail
