# slack-exporter

Export Slack channel messages to a JSONL file using [latchkey](https://github.com/nichochar/latchkey) for authentication.

## Prerequisites

- [latchkey](https://github.com/nichochar/latchkey) installed and configured with Slack credentials:
  ```bash
  npm install -g latchkey
  latchkey auth browser slack
  ```

## Usage

```bash
# Export #general (default) starting from 2024-01-01
slack-exporter

# Export specific channels
slack-exporter --channels general random engineering

# Export with per-channel start dates
slack-exporter --channels "general:2024-01-01" "random:2024-06-01"

# Set a global start date
slack-exporter --since 2023-01-01

# Custom output file
slack-exporter --output my_slack_data.jsonl

# Verbose logging
slack-exporter -v
```

## How it works

1. Reads the existing JSONL file (if any) to understand what messages have already been exported
2. Fetches the channel list from Slack (via `conversations.list`) to resolve channel names to IDs
3. For each configured channel, fetches new messages (via `conversations.history`) starting from either the configured oldest date or the most recent message already in the file
4. Appends all new data to the JSONL file

The JSONL file contains two kinds of records:
- `CHANNEL_INFO`: channel metadata from `conversations.list`
- `MESSAGE`: individual messages from `conversations.history`

Each record includes the raw Slack API response, so no data is lost.

Running the exporter multiple times is safe -- it only appends new messages.
