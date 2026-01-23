have to be careful with offline mode here:
    we could install hooks such that periodically, and while shutting down, we snapshotted some data into the agent state dir
    and then if the machine is offline, we could try using that data instead (and make a note that we seems offline)

## TODO

The git_status plugin is not implemented. The following features need to be built:

- Plugin implementation that populates `plugin.git_status` namespace
- `plugin.git_status.branch` - Current git branch (partial: `get_current_git_branch()` exists in git_utils.py but not exposed as plugin data)
- `plugin.git_status.commit` - Current git commit hash
- `plugin.git_status.repo_url` - Remote repository URL
- `plugin.git_status.url` - Agent repository URL
- `plugin.git_status.has_uncommitted_changes` - Boolean for uncommitted changes
- `plugin.git_status.has_unpushed_commits` - Boolean for unpushed commits
- `plugin.git_status.has_untracked_files` - Boolean for untracked files
- `plugin.git_status.modified_file_count` - Number of modified files
- `plugin.git_status.untracked_file_count` - Number of untracked files
- `plugin.git_status.additions` - Number of added lines
- `plugin.git_status.deletions` - Number of deleted lines
