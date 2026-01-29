# Offline Mngr State Spec [future]

Do need to be careful that, when shutting down, the offline state plugin does its upload at the very last moment...
    otherwise stuff like the git_status plugin, which creates state during shutdown, won't have their state saved.

Note: The following features are planned but not yet implemented: plugin module structure, local directory storage backend with rsync, S3 storage backend with AWS CLI, configuration handling (save_interval_seconds, storage_backend, local_directory, s3_bucket, s3_region), periodic save mechanism, on_host_destroyed hook integration, write-only credentials validation for S3, rrsync for local backend security, lifecycle hooks wiring, last-execution ordering during shutdown.
