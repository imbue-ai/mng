# Commands that target from multiple hosts/agents

Commands that target multiple agents/hosts must specify the behavior when the command fail for some of those hosts (ex: due to state transitions like shutting down, etc)

The options are:

- continue-and-warn: proceed with the command and log warnings for any hosts where the command did not succeed
- fail-immediately: abort the command as soon as a command fails on any host
- retry-until-success: keep retrying until all hosts have succeeded
