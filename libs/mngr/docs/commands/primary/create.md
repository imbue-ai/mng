<!-- This file is auto-generated. Do not edit directly. -->
<!-- To modify, edit the command's help metadata and run: uv run python scripts/make_cli_docs.py -->

# mngr create

**Synopsis:**

```text
mngr [create|c] [<AGENT_NAME>] [<AGENT_TYPE>] [-t <TEMPLATE>] [--in <PROVIDER>] [--host <HOST>] [--c WINDOW_NAME=COMMAND]
    [--tag KEY=VALUE] [--project <PROJECT>] [--from <SOURCE>] [--in-place|--copy|--clone|--worktree]
    [--[no-]rsync] [--rsync-args <ARGS>] [--base-branch <BRANCH>] [--new-branch [<BRANCH-NAME>]] [--[no-]ensure-clean]
    [--snapshot <ID>] [-b <BUILD_ARG>] [-s <START_ARG>]
    [--env <KEY=VALUE>] [--env-file <FILE>] [--grant <PERMISSION>] [--user-command <COMMAND>] [--upload-file <LOCAL:REMOTE>]
    [--idle-timeout <SECONDS>] [--idle-mode <MODE>] [--start-on-boot|--no-start-on-boot] [--reuse|--no-reuse]
    [--[no-]auto-start] [--] [<AGENT_ARGS>...]
```


Create and run an agent.

Sets up the agent's work_dir, optionally provisions a new host (or uses
an existing one), runs the specified agent, and connects to it (by default).

Alias: c

**Usage:**

```text
mngr create [OPTIONS] [POSITIONAL_NAME] [POSITIONAL_AGENT_TYPE]
            [AGENT_ARGS]...
```

## Arguments

- `NAME`: Name for the agent (auto-generated if not provided)
- `AGENT_TYPE`: Which type of agent to run (default: `claude`). Can also be specified via `--agent-type`
- `AGENT_ARGS`: Additional arguments passed to the agent

**Options:**

## Agent Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-t`, `--template` | text | Use a named template from create_templates config [repeatable, stacks in order] | None |
| `-n`, `--name` | text | Agent name (alternative to positional argument) [default: auto-generated] | None |
| `--name-style` | choice (`english` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `animals` &#x7C; `scientists` &#x7C; `demons`) | Auto-generated name style | `english` |
| `--agent-type` | text | Which type of agent to run [default: claude] | None |
| `--agent-cmd`, `--agent-command` | text | Run a literal command using the generic agent type (mutually exclusive with --agent-type) | None |
| `-c`, `--add-cmd`, `--add-command` | text | Run extra command in additional window. Use name="command" to set window name. Note: ALL_UPPERCASE names (e.g., FOO="bar") are treated as env var assignments, not window names | None |
| `--user` | text | Override which user to run the agent as [default: current user for local, provider-defined or root for remote] | None |

## Host Options

By default, `mngr create` uses the "local" host. Use these options to change that behavior.

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--in`, `--new-host` | text | Create a new host using provider (docker, modal, ...) | None |
| `--host`, `--target-host` | text | Use an existing host (by name or ID) [default: local] | None |
| `--project` | text | Project name for the agent [default: derived from git remote origin or folder name] | None |
| `--tag` | text | Metadata tag KEY=VALUE [repeatable] | None |
| `--host-name` | text | Name for the new host | None |
| `--host-name-style` | choice (`astronomy` &#x7C; `places` &#x7C; `cities` &#x7C; `fantasy` &#x7C; `scifi` &#x7C; `painters` &#x7C; `authors` &#x7C; `artists` &#x7C; `musicians` &#x7C; `scientists`) | Auto-generated host name style | `astronomy` |

## Behavior

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--reuse`, `--no-reuse` | boolean | Reuse existing agent with the same name if it exists (idempotent create) | `False` |
| `--connect`, `--no-connect` | boolean | Connect to the agent after creation [default: connect] | `True` |
| `--await-ready`, `--no-await-ready` | boolean | Wait until agent is ready before returning [default: no-await-ready if --no-connect] | None |
| `--await-agent-stopped`, `--no-await-agent-stopped` | boolean | Wait until agent has completely finished running before exiting. Useful for testing and scripting. First waits for agent to become ready, then waits for it to stop. [default: no-await-agent-stopped] | None |
| `--ensure-clean`, `--no-ensure-clean` | boolean | Abort if working tree is dirty | `True` |
| `--snapshot-source`, `--no-snapshot-source` | boolean | Snapshot source agent first [default: yes if --source-agent and not local] | None |
| `--copy-work-dir`, `--no-copy-work-dir` | boolean | Copy source work_dir immediately. Useful when launching background agents so you can continue editing locally without changes being copied to the new agent [default: copy if --no-connect, no-copy if --connect] | None |
| `--auto-start`, `--no-auto-start` | boolean | Automatically start offline hosts (source and target) before proceeding | `True` |

## Agent Source Data (what to include in the new agent)

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--from`, `--source` | text | Directory to use as work_dir root [AGENT &#x7C; AGENT.HOST &#x7C; AGENT.HOST:PATH &#x7C; HOST:PATH]. Defaults to current dir if no other source args are given | None |
| `--source-agent`, `--from-agent` | text | Source agent for cloning work_dir | None |
| `--source-host` | text | Source host | None |
| `--source-path` | text | Source path | None |
| `--rsync`, `--no-rsync` | boolean | Use rsync for file transfer [default: yes if rsync-args are present or if git is disabled] | None |
| `--rsync-args` | text | Additional arguments to pass to rsync | None |
| `--include-git`, `--no-include-git` | boolean | Include .git directory | `True` |
| `--include-unclean`, `--exclude-unclean` | boolean | Include uncommitted files [default: include if --no-ensure-clean] | None |
| `--include-gitignored`, `--no-include-gitignored` | boolean | Include gitignored files | `False` |

## Agent Target (where to put the new agent)

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--target` | text | Target [HOST][:PATH]. Defaults to current dir if no other target args are given | None |
| `--target-path` | text | Directory to mount source inside agent host. Incompatible with --in-place | None |
| `--in-place` | boolean | Run directly in source directory. Incompatible with --target-path | `False` |
| `--copy` | boolean | Copy source to isolated directory before running [default for remote agents, and for local agents if not in a git repo] | `False` |
| `--clone` | boolean | Create a git clone that shares objects with original repo (only works for local agents) | `False` |
| `--worktree` | boolean | Create a git worktree that shares objects and index with original repo [default for local agents in a git repo]. Requires --new-branch (which is the default) | `False` |

## Agent Git Configuration

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--base-branch` | text | The starting point for the agent [default: current branch] | None |
| `--new-branch` | text | Create a fresh branch (named TEXT if provided, otherwise auto-generated) [default: new branch] | `` |
| `--no-new-branch` | boolean | Do not create a new branch; use the current branch directly. Incompatible with --worktree | None |
| `--new-branch-prefix` | text | Prefix for auto-generated branch names | `mngr/` |
| `--depth` | integer | Shallow clone depth [default: full] | None |
| `--shallow-since` | text | Shallow clone since date | None |

## Agent Environment Variables

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--env`, `--agent-env` | text | Set environment variable KEY=VALUE | None |
| `--env-file`, `--agent-env-file` | path | Load env | None |
| `--pass-env`, `--pass-agent-env` | text | Forward variable from shell | None |

## Agent Provisioning

See [Provision Options](../secondary/provision.md) for full details.

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--grant` | text | Grant a permission to the agent [repeatable] | None |
| `--user-command` | text | Run custom shell command during provisioning [repeatable] | None |
| `--sudo-command` | text | Run custom shell command as root during provisioning [repeatable] | None |
| `--upload-file` | text | Upload LOCAL:REMOTE file pair [repeatable] | None |
| `--append-to-file` | text | Append REMOTE:TEXT to file [repeatable] | None |
| `--prepend-to-file` | text | Prepend REMOTE:TEXT to file [repeatable] | None |
| `--create-directory` | text | Create directory on remote [repeatable] | None |

## New Host Environment Variables

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--host-env` | text | Set environment variable KEY=VALUE for host [repeatable] | None |
| `--host-env-file` | path | Load env file for host [repeatable] | None |
| `--pass-host-env` | text | Forward variable from shell for host [repeatable] | None |
| `--known-host` | text | SSH known_hosts entry to add to the host (for outbound SSH) [repeatable] | None |

## New Host Build

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--snapshot` | text | Use existing snapshot instead of building | None |
| `-b`, `--build`, `--build-arg` | text | Build argument as key=value or --key=value (e.g., -b gpu=h100 -b cpu=2) [repeatable] | None |
| `--build-args` | text | Space-separated build arguments (e.g., 'gpu=h100 cpu=2') | None |
| `-s`, `--start`, `--start-arg` | text | Argument for start [repeatable] | None |
| `--start-args` | text | Space-separated start arguments (alternative to -s) | None |

## New Host Lifecycle

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--idle-timeout` | text | Shutdown after idle for specified duration (e.g., 30s, 5m, 1h, or plain seconds) [default: none] | None |
| `--idle-mode` | choice (`io` &#x7C; `user` &#x7C; `agent` &#x7C; `ssh` &#x7C; `create` &#x7C; `boot` &#x7C; `start` &#x7C; `run` &#x7C; `custom` &#x7C; `disabled`) | When to consider host idle [default: io if remote, disabled if local] | None |
| `--activity-sources` | text | Activity sources for idle detection (comma-separated) | None |
| `--start-on-boot`, `--no-start-on-boot` | boolean | Restart on host boot [default: no] | None |

## Connection Options

See [connect options](./connect.md) for full details (only applies if `--connect` is specified).

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--reconnect`, `--no-reconnect` | boolean | Automatically reconnect if dropped | `True` |
| `--interactive`, `--no-interactive` | boolean | Enable interactive mode [default: yes if TTY] | None |
| `--message` | text | Initial message to send after the agent starts | None |
| `--message-file` | path | File containing initial message to send | None |
| `--edit-message` | boolean | Open an editor to compose the initial message (uses $EDITOR). Editor runs in parallel with agent creation. If --message or --message-file is provided, their content is used as initial editor content. | `False` |
| `--resume-message` | text | Message to send when the agent is started (resumed) after being stopped | None |
| `--resume-message-file` | path | File containing resume message to send on start | None |
| `--ready-timeout` | float | Timeout in seconds to wait for agent readiness before sending initial message | `10.0` |
| `--retry` | integer | Number of connection retries | `3` |
| `--retry-delay` | text | Delay between retries (e.g., 5s, 1m) | `5s` |
| `--attach-command` | text | Command to run instead of attaching to main session | None |

## Automation

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-y`, `--yes` | boolean | Auto-approve all prompts (e.g., skill installation) without asking | `False` |

## Common

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `--format` | text | Output format (human, json, jsonl, FORMAT): Output format for results. When a template is provided, fields use standard python templating like 'name: {agent.name}' See below for available fields. | `human` |
| `--json` | boolean | Alias for --format json | `False` |
| `--jsonl` | boolean | Alias for --format jsonl | `False` |
| `-q`, `--quiet` | boolean | Suppress all console output | `False` |
| `-v`, `--verbose` | integer range | Increase verbosity (default: BUILD); -v for DEBUG, -vv for TRACE | `0` |
| `--log-file` | path | Path to log file (overrides default ~/.mngr/logs/<timestamp>-<pid>.json) | None |
| `--log-commands`, `--no-log-commands` | boolean | Log commands that were executed | None |
| `--log-command-output`, `--no-log-command-output` | boolean | Log stdout/stderr from commands | None |
| `--log-env-vars`, `--no-log-env-vars` | boolean | Log environment variables (security risk) | None |
| `--context` | path | Project context directory (for build context and loading project-specific config) [default: local .git root] | None |
| `--plugin`, `--enable-plugin` | text | Enable a plugin [repeatable] | None |
| `--disable-plugin` | text | Disable a plugin [repeatable] | None |

## Other Options

| Name | Type | Description | Default |
| ---- | ---- | ----------- | ------- |
| `-h`, `--help` | boolean | Show this message and exit. | `False` |

## Agent Limits

See [Limit Options](../secondary/limit.md)


## Provider Build/Start Arguments

Provider: docker
  Arguments are passed directly to 'docker build'.

  Start a build

  Usage:  docker buildx build [OPTIONS] PATH | URL | -

  Start a build

  Aliases:
    docker build, docker builder build, docker image build, docker buildx b

  Options:
        --add-host strings              Add a custom host-to-IP mapping
                                        (format: "host:ip")
        --allow stringArray             Allow extra privileged entitlement
                                        (e.g., "network.host",
                                        "security.insecure")
        --annotation stringArray        Add annotation to the image
        --attest stringArray            Attestation parameters (format:
                                        "type=sbom,generator=image")
        --build-arg stringArray         Set build-time variables
        --build-context stringArray     Additional build contexts (e.g.,
                                        name=path)
        --builder string                Override the configured builder
                                        instance (default "default")
        --cache-from stringArray        External cache sources (e.g.,
                                        "user/app:cache",
                                        "type=local,src=path/to/dir")
        --cache-to stringArray          Cache export destinations (e.g.,
                                        "user/app:cache",
                                        "type=local,dest=path/to/dir")
        --call string                   Set method for evaluating build
                                        ("check", "outline", "targets")
                                        (default "build")
        --cgroup-parent string          Set the parent cgroup for the "RUN"
                                        instructions during build
        --check                         Shorthand for "--call=check" (default )
    -D, --debug                         Enable debug logging
    -f, --file string                   Name of the Dockerfile (default:
                                        "PATH/Dockerfile")
        --iidfile string                Write the image ID to a file
        --label stringArray             Set metadata for an image
        --load                          Shorthand for "--output=type=docker"
        --metadata-file string          Write build result metadata to a file
        --network string                Set the networking mode for the
                                        "RUN" instructions during build
                                        (default "default")
        --no-cache                      Do not use cache when building the image
        --no-cache-filter stringArray   Do not cache specified stages
    -o, --output stringArray            Output destination (format:
                                        "type=local,dest=path")
        --platform stringArray          Set target platform for build
        --progress string               Set type of progress output
                                        ("auto", "quiet", "plain", "tty",
                                        "rawjson"). Use plain to show
                                        container output (default "auto")
        --provenance string             Shorthand for "--attest=type=provenance"
        --pull                          Always attempt to pull all
                                        referenced images
        --push                          Shorthand for "--output=type=registry"
    -q, --quiet                         Suppress the build output and print
                                        image ID on success
        --sbom string                   Shorthand for "--attest=type=sbom"
        --secret stringArray            Secret to expose to the build
                                        (format:
                                        "id=mysecret[,src=/local/secret]")
        --shm-size bytes                Shared memory size for build containers
        --ssh stringArray               SSH agent socket or keys to expose
                                        to the build (format:
                                        "default|<id>[=<socket>|<key>[,<key>]]")
    -t, --tag stringArray               Name and optionally a tag (format:
                                        "name:tag")
        --target string                 Set the target build stage to build
        --ulimit ulimit                 Ulimit options (default [])

  Experimental commands and flags are hidden. Set BUILDX_EXPERIMENTAL=1 to show them.
  Arguments are passed directly to 'docker run'.

  Usage:  docker run [OPTIONS] IMAGE [COMMAND] [ARG...]

  Create and run a new container from an image

  Aliases:
    docker container run, docker run

  Options:
        --add-host list                    Add a custom host-to-IP mapping
                                           (host:ip)
        --annotation map                   Add an annotation to the
                                           container (passed through to the
                                           OCI runtime) (default map[])
    -a, --attach list                      Attach to STDIN, STDOUT or STDERR
        --blkio-weight uint16              Block IO (relative weight),
                                           between 10 and 1000, or 0 to
                                           disable (default 0)
        --blkio-weight-device list         Block IO weight (relative device
                                           weight) (default [])
        --cap-add list                     Add Linux capabilities
        --cap-drop list                    Drop Linux capabilities
        --cgroup-parent string             Optional parent cgroup for the
                                           container
        --cgroupns string                  Cgroup namespace to use
                                           (host|private)
                                           'host':    Run the container in
                                           the Docker host's cgroup
                                           namespace
                                           'private': Run the container in
                                           its own private cgroup namespace
                                           '':        Use the cgroup
                                           namespace as configured by the
                                                      default-cgroupns-mode
                                           option on the daemon (default)
        --cidfile string                   Write the container ID to the file
        --cpu-period int                   Limit CPU CFS (Completely Fair
                                           Scheduler) period
        --cpu-quota int                    Limit CPU CFS (Completely Fair
                                           Scheduler) quota
        --cpu-rt-period int                Limit CPU real-time period in
                                           microseconds
        --cpu-rt-runtime int               Limit CPU real-time runtime in
                                           microseconds
    -c, --cpu-shares int                   CPU shares (relative weight)
        --cpus decimal                     Number of CPUs
        --cpuset-cpus string               CPUs in which to allow execution
                                           (0-3, 0,1)
        --cpuset-mems string               MEMs in which to allow execution
                                           (0-3, 0,1)
    -d, --detach                           Run container in background and
                                           print container ID
        --detach-keys string               Override the key sequence for
                                           detaching a container
        --device list                      Add a host device to the container
        --device-cgroup-rule list          Add a rule to the cgroup allowed
                                           devices list
        --device-read-bps list             Limit read rate (bytes per
                                           second) from a device (default [])
        --device-read-iops list            Limit read rate (IO per second)
                                           from a device (default [])
        --device-write-bps list            Limit write rate (bytes per
                                           second) to a device (default [])
        --device-write-iops list           Limit write rate (IO per second)
                                           to a device (default [])
        --disable-content-trust            Skip image verification (default
                                           true)
        --dns list                         Set custom DNS servers
        --dns-option list                  Set DNS options
        --dns-search list                  Set custom DNS search domains
        --domainname string                Container NIS domain name
        --entrypoint string                Overwrite the default ENTRYPOINT
                                           of the image
    -e, --env list                         Set environment variables
        --env-file list                    Read in a file of environment
                                           variables
        --expose list                      Expose a port or a range of ports
        --gpus gpu-request                 GPU devices to add to the
                                           container ('all' to pass all GPUs)
        --group-add list                   Add additional groups to join
        --health-cmd string                Command to run to check health
        --health-interval duration         Time between running the check
                                           (ms|s|m|h) (default 0s)
        --health-retries int               Consecutive failures needed to
                                           report unhealthy
        --health-start-interval duration   Time between running the check
                                           during the start period
                                           (ms|s|m|h) (default 0s)
        --health-start-period duration     Start period for the container
                                           to initialize before starting
                                           health-retries countdown
                                           (ms|s|m|h) (default 0s)
        --health-timeout duration          Maximum time to allow one check
                                           to run (ms|s|m|h) (default 0s)
        --help                             Print usage
    -h, --hostname string                  Container host name
        --init                             Run an init inside the container
                                           that forwards signals and reaps
                                           processes
    -i, --interactive                      Keep STDIN open even if not attached
        --ip string                        IPv4 address (e.g., 172.30.100.104)
        --ip6 string                       IPv6 address (e.g., 2001:db8::33)
        --ipc string                       IPC mode to use
        --isolation string                 Container isolation technology
        --kernel-memory bytes              Kernel memory limit
    -l, --label list                       Set meta data on a container
        --label-file list                  Read in a line delimited file of
                                           labels
        --link list                        Add link to another container
        --link-local-ip list               Container IPv4/IPv6 link-local
                                           addresses
        --log-driver string                Logging driver for the container
        --log-opt list                     Log driver options
        --mac-address string               Container MAC address (e.g.,
                                           92:d0:c6:0a:29:33)
    -m, --memory bytes                     Memory limit
        --memory-reservation bytes         Memory soft limit
        --memory-swap bytes                Swap limit equal to memory plus
                                           swap: '-1' to enable unlimited swap
        --memory-swappiness int            Tune container memory swappiness
                                           (0 to 100) (default -1)
        --mount mount                      Attach a filesystem mount to the
                                           container
        --name string                      Assign a name to the container
        --network network                  Connect a container to a network
        --network-alias list               Add network-scoped alias for the
                                           container
        --no-healthcheck                   Disable any container-specified
                                           HEALTHCHECK
        --oom-kill-disable                 Disable OOM Killer
        --oom-score-adj int                Tune host's OOM preferences
                                           (-1000 to 1000)
        --pid string                       PID namespace to use
        --pids-limit int                   Tune container pids limit (set
                                           -1 for unlimited)
        --platform string                  Set platform if server is
                                           multi-platform capable
        --privileged                       Give extended privileges to this
                                           container
    -p, --publish list                     Publish a container's port(s) to
                                           the host
    -P, --publish-all                      Publish all exposed ports to
                                           random ports
        --pull string                      Pull image before running
                                           ("always", "missing", "never")
                                           (default "missing")
    -q, --quiet                            Suppress the pull output
        --read-only                        Mount the container's root
                                           filesystem as read only
        --restart string                   Restart policy to apply when a
                                           container exits (default "no")
        --rm                               Automatically remove the
                                           container and its associated
                                           anonymous volumes when it exits
        --runtime string                   Runtime to use for this container
        --security-opt list                Security Options
        --shm-size bytes                   Size of /dev/shm
        --sig-proxy                        Proxy received signals to the
                                           process (default true)
        --stop-signal string               Signal to stop the container
        --stop-timeout int                 Timeout (in seconds) to stop a
                                           container
        --storage-opt list                 Storage driver options for the
                                           container
        --sysctl map                       Sysctl options (default map[])
        --tmpfs list                       Mount a tmpfs directory
    -t, --tty                              Allocate a pseudo-TTY
        --ulimit ulimit                    Ulimit options (default [])
        --use-api-socket                   Bind mount Docker API socket and
                                           required auth
    -u, --user string                      Username or UID (format:
                                           <name|uid>[:<group|gid>])
        --userns string                    User namespace to use
        --uts string                       UTS namespace to use
    -v, --volume list                      Bind mount a volume
        --volume-driver string             Optional volume driver for the
                                           container
        --volumes-from list                Mount volumes from the specified
                                           container(s)
    -w, --workdir string                   Working directory inside the
                                           container

Provider: local
  No build arguments are supported for the local provider.
  No start arguments are supported for the local provider.

Provider: modal
  Supported build arguments for the modal provider:
    --gpu TYPE            GPU type to use (e.g., t4, a10g, a100, any). Default: no GPU
    --cpu COUNT           Number of CPU cores (0.25-16). Default: 1.0
    --memory GB           Memory in GB (0.5-32). Default: 1.0
    --image NAME          Base Docker image to use. Default: debian:bookworm-slim
    --timeout SEC         Maximum sandbox lifetime in seconds. Default: 900 (15 min)
    --region NAME         Region to run the sandbox in (e.g., us-east, us-west, eu-west). Default: auto
    --context-dir DIR     Build context directory for Dockerfile COPY/ADD instructions. Default: Dockerfile's directory
    --secret VAR          Pass an environment variable as a secret to the image build. The value of
                          VAR is read from your current environment and made available during Dockerfile
                          RUN commands via --mount=type=secret,id=VAR. Can be specified multiple times.
    --cidr-allowlist CIDR Restrict network access to the specified CIDR range (e.g., 203.0.113.0/24).
                          Can be specified multiple times.
    --offline             Block all outbound network access from the sandbox. Default: off
    --volume NAME:PATH    Mount a persistent Modal Volume at PATH inside the sandbox. NAME is the
                          volume name on Modal (created if it doesn't exist). Can be specified
                          multiple times.
  No start arguments are supported for the modal provider.

Provider: ssh
  The SSH provider does not support creating hosts dynamically.
  Hosts must be pre-configured in the mngr config file.

  Example configuration in mngr.toml:
    [providers.my-ssh-pool]
    backend = "ssh"

    [providers.my-ssh-pool.hosts.server1]
    address = "192.168.1.100"
    port = 22
    user = "root"
    key_file = "~/.ssh/id_ed25519"
  No start arguments are supported for the SSH provider.


## See Also

- [mngr connect](./connect.md) - Connect to an existing agent
- [mngr list](./list.md) - List existing agents
- [mngr destroy](./destroy.md) - Destroy agents

## Examples

**Create an agent locally in a new git worktree (default)**

```bash
$ mngr create my-agent
```

**Create an agent in a Docker container**

```bash
$ mngr create my-agent --in docker
```

**Create an agent in a Modal sandbox**

```bash
$ mngr create my-agent --in modal
```

**Create using a named template**

```bash
$ mngr create my-agent --template modal
```

**Stack multiple templates**

```bash
$ mngr create my-agent -t modal -t codex
```

**Create a codex agent instead of claude**

```bash
$ mngr create my-agent codex
```

**Pass arguments to the agent**

```bash
$ mngr create my-agent -- --model opus
```

**Create on an existing host**

```bash
$ mngr create my-agent --host my-dev-box
```

**Clone from an existing agent**

```bash
$ mngr create new-agent --source other-agent
```

**Run directly in-place (no worktree)**

```bash
$ mngr create my-agent --in-place
```

**Create without connecting**

```bash
$ mngr create my-agent --no-connect
```

**Add extra tmux windows**

```bash
$ mngr create my-agent -c server="npm run dev"
```

**Reuse existing agent or create if not found**

```bash
$ mngr create my-agent --reuse
```
