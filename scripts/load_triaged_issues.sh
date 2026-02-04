#!/usr/bin/env bash
#
# Load triaged GitHub issues with the 'autoclaude' label.
#
# This script fetches all open issues labeled 'autoclaude' and filters them
# to only include issues that have comments from authorized users. The output
# is a JSON object with an 'issues' array containing the filtered issues.
#
# Usage:
#     ./scripts/load_triaged_issues.sh > triaged_issues.json
#
# Dependencies: gh, jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/authorized_github_users.toml"

# Load authorized users from TOML config
load_authorized_users() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "Error: authorized_github_users.toml not found at $CONFIG_FILE" >&2
        exit 1
    fi

    # Extract usernames from the TOML array, handling quotes and whitespace
    grep -E '^\s*"[^"]+"\s*,?\s*$' "$CONFIG_FILE" | \
        sed 's/.*"\([^"]*\)".*/\1/' | \
        tr '\n' '|' | \
        sed 's/|$//'
}

# Fetch all open issues with the 'autoclaude' label
fetch_autoclaude_issues() {
    gh issue list \
        --label "autoclaude" \
        --state open \
        --json number,title,body,labels,createdAt,url \
        --limit 1000
}

# Fetch comments for a specific issue
fetch_issue_comments() {
    local issue_number="$1"
    gh issue view "$issue_number" --json comments --jq '.comments'
}

# Main processing
main() {
    local authorized_users_pattern
    authorized_users_pattern=$(load_authorized_users)

    if [[ -z "$authorized_users_pattern" ]]; then
        echo "Error: No authorized users found in config" >&2
        exit 1
    fi

    echo "Loaded authorized users: ${authorized_users_pattern//|/, }" >&2

    # Fetch all autoclaude issues
    local issues
    issues=$(fetch_autoclaude_issues)

    local issue_count
    issue_count=$(echo "$issues" | jq 'length')
    echo "Found $issue_count open issues with 'autoclaude' label" >&2

    # Process each issue and filter comments
    local triaged_issues="[]"

    while read -r issue_number; do
        [[ -z "$issue_number" ]] && continue

        # Fetch comments for this issue
        local comments
        comments=$(fetch_issue_comments "$issue_number")

        # Filter to only authorized user comments
        local filtered_comments
        filtered_comments=$(echo "$comments" | jq --arg pattern "$authorized_users_pattern" '
            [.[] | select(.author.login | test("^(" + $pattern + ")$"))] |
            map({
                author: .author.login,
                body: .body,
                created_at: .createdAt
            })
        ')

        local comment_count
        comment_count=$(echo "$filtered_comments" | jq 'length')

        # Only include issues with at least one authorized comment
        if [[ "$comment_count" -gt 0 ]]; then
            echo "Issue #$issue_number: $comment_count authorized comment(s)" >&2

            # Get the issue data and add filtered comments
            local issue_data
            issue_data=$(echo "$issues" | jq --argjson num "$issue_number" --argjson comments "$filtered_comments" '
                .[] | select(.number == $num) |
                {
                    number: .number,
                    title: .title,
                    body: .body,
                    labels: [.labels[].name],
                    created_at: .createdAt,
                    url: .url,
                    authorized_comments: $comments
                }
            ')

            triaged_issues=$(echo "$triaged_issues" | jq --argjson issue "$issue_data" '. + [$issue]')
        fi
    done < <(echo "$issues" | jq -r '.[].number')

    local triaged_count
    triaged_count=$(echo "$triaged_issues" | jq 'length')
    echo "Total triaged issues: $triaged_count" >&2

    # Output the final result
    echo "$triaged_issues" | jq '{issues: .}'
}

main "$@"
