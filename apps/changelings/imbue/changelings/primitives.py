from imbue.imbue_common.primitives import NonEmptyStr


class ChangelingName(NonEmptyStr):
    """The unique name identifying a changeling (e.g., 'fixme-fairy', 'test-troll')."""

    ...


class CronSchedule(NonEmptyStr):
    """A cron expression defining when a changeling runs (e.g., '0 3 * * *' for 3am daily)."""

    ...


class ChangelingTemplateName(NonEmptyStr):
    """The name of a built-in changeling template (e.g., 'fixme-fairy', 'coverage-hunter')."""

    ...


class GitRepoUrl(NonEmptyStr):
    """A git repository URL (HTTPS or SSH) that a changeling targets."""

    ...
