# mng project context

The following files are injected into the system prompt so you do not need to read them manually.

## README files

- @README.md
- @imbue/mng/README.md
- @imbue/mng/providers/docker/README.md

## User-facing documentation (docs/)

- @docs/architecture.md
- @docs/principles.md
- @docs/conventions.md
- @docs/all_supported_agents.md
- @docs/api.md
- @docs/customization.md
- @docs/faq.md
- @docs/future_work.md
- @docs/security_model.md
- @docs/nested_tmux.md
- @docs/concepts/agents.md
- @docs/concepts/agent_types.md
- @docs/concepts/api.md
- @docs/concepts/environment_variables.md
- @docs/concepts/hosts.md
- @docs/concepts/idle_detection.md
- @docs/concepts/permissions.md
- @docs/concepts/plugins.md
- @docs/concepts/provider_backends.md
- @docs/concepts/providers.md
- @docs/concepts/provisioning.md
- @docs/concepts/snapshot.md
- @docs/commands/primary/connect.md
- @docs/commands/primary/create.md
- @docs/commands/primary/destroy.md
- @docs/commands/primary/exec.md
- @docs/commands/primary/list.md
- @docs/commands/primary/open.md
- @docs/commands/primary/pair.md
- @docs/commands/primary/pull.md
- @docs/commands/primary/push.md
- @docs/commands/primary/rename.md
- @docs/commands/primary/start.md
- @docs/commands/primary/stop.md
- @docs/commands/secondary/ask.md
- @docs/commands/secondary/cleanup.md
- @docs/commands/secondary/config.md
- @docs/commands/secondary/gc.md
- @docs/commands/secondary/limit.md
- @docs/commands/secondary/logs.md
- @docs/commands/secondary/message.md
- @docs/commands/secondary/plugin.md
- @docs/commands/secondary/provision.md
- @docs/commands/secondary/snapshot.md
- @docs/commands/aliases/clone.md
- @docs/commands/aliases/migrate.md
- @docs/commands/generic/common.md
- @docs/commands/generic/multi_target.md
- @docs/commands/generic/resource_cleanup.md
- @docs/core_plugins/agent_data_url.md
- @docs/core_plugins/default_url_for_cli_agents_via_ttyd.md
- @docs/core_plugins/git_status.md
- @docs/core_plugins/host_data_url.md
- @docs/core_plugins/local_port_forwarding_via_frp_and_nginx.md
- @docs/core_plugins/offline_mng_state.md
- @docs/core_plugins/user_activity_tracking_via_web.md
- @docs/core_plugins/agents/claude_code.md
- @docs/core_plugins/agents/codex_cli.md
- @docs/core_plugins/agents/opencode.md
- @docs/core_plugins/providers/docker.md
- @docs/core_plugins/providers/local.md
- @docs/core_plugins/providers/modal.md

## Core source files

### Root module files

- @imbue/mng/primitives.py
- @imbue/mng/errors.py
- @imbue/mng/main.py
- @imbue/mng/conftest.py

### Interfaces

- @imbue/mng/interfaces/agent.py
- @imbue/mng/interfaces/data_types.py
- @imbue/mng/interfaces/host.py
- @imbue/mng/interfaces/provider_backend.py
- @imbue/mng/interfaces/provider_instance.py
- @imbue/mng/interfaces/volume.py

### Utils

- @imbue/mng/utils/cel_utils.py
- @imbue/mng/utils/deps.py
- @imbue/mng/utils/duration.py
- @imbue/mng/utils/editor.py
- @imbue/mng/utils/env_utils.py
- @imbue/mng/utils/git_utils.py
- @imbue/mng/utils/interactive_subprocess.py
- @imbue/mng/utils/logging.py
- @imbue/mng/utils/name_generator.py
- @imbue/mng/utils/polling.py
- @imbue/mng/utils/rsync_utils.py

### Data types (across modules)

- @imbue/mng/config/data_types.py
- @imbue/mng/config/loader.py
- @imbue/mng/config/plugin_registry.py
- @imbue/mng/api/data_types.py
- @imbue/mng/cli/data_types.py
