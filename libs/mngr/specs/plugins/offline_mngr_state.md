do need to be careful that, when shutting down, the offline state plugin does its upload at the very last moment...
    otherwise stuff like the git_status plugin, which creates state during shutdown, won't have their state saved.

## TODOs

**Status: Plugin is completely unimplemented.**

- Create plugin module structure in `default_plugins/offline_mngr_state.py`
- Implement local directory storage backend with rsync synchronization
- Implement S3 storage backend with AWS CLI integration
- Add configuration handling (save_interval_seconds, storage_backend, local_directory, s3_bucket, s3_region)
- Implement periodic save mechanism using timer-based state backups
- Hook into `on_host_destroyed` to save state on host shutdown
- Validate write-only credentials for S3 backend
- Integrate rrsync (restricted rsync) for local backend security
- Wire up lifecycle hooks (`on_host_destroyed`, `on_agent_destroyed`) to be called by host/agent management code
- Ensure plugin executes last during shutdown to capture final state from other plugins
