import time

from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.pure import pure
from imbue.mng.api.list import list_agents
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.data_types import AgentInfo
from imbue.mng.primitives import ErrorBehavior
from imbue.mng.primitives import LOCAL_PROVIDER_NAME
from imbue.mng.utils.git_utils import get_current_git_branch
from imbue.mng_pankan.data_types import AgentBoardEntry
from imbue.mng_pankan.data_types import BoardSnapshot
from imbue.mng_pankan.data_types import PrInfo
from imbue.mng_pankan.data_types import PrState
from imbue.mng_pankan.github import fetch_all_prs


def fetch_board_snapshot(mng_ctx: MngContext) -> BoardSnapshot:
    """Fetch a complete board snapshot: agents, branches, and PR associations.

    Lists all agents, fetches GitHub PRs, resolves each agent's branch,
    and matches agents to PRs by branch name.
    """
    start_time = time.monotonic()
    errors: list[str] = []
    cg = mng_ctx.concurrency_group

    # List all agents (continue on errors to show partial results)
    result = list_agents(mng_ctx, is_streaming=False, error_behavior=ErrorBehavior.CONTINUE)
    for error in result.errors:
        errors.append(f"{error.exception_type}: {error.message}")

    # Fetch all PRs from GitHub
    prs = fetch_all_prs(cg)
    pr_by_branch = _build_pr_branch_index(prs)

    # Build board entries with branch and PR info
    entries: list[AgentBoardEntry] = []
    for agent in result.agents:
        branch = _resolve_agent_branch(agent, cg)
        pr = pr_by_branch.get(branch) if branch else None
        entries.append(
            AgentBoardEntry(
                name=agent.name,
                state=agent.state,
                provider_name=agent.host.provider_name,
                branch=branch,
                pr=pr,
            )
        )

    elapsed = time.monotonic() - start_time
    return BoardSnapshot(
        entries=tuple(entries),
        errors=tuple(errors),
        fetch_time_seconds=elapsed,
    )


def _resolve_agent_branch(agent: AgentInfo, cg: ConcurrencyGroup) -> str | None:
    """Determine the git branch associated with an agent.

    For local agents with an accessible work_dir, reads the branch via git.
    Falls back to the naming convention mng/<name>-<provider>.
    """
    if agent.host.provider_name == LOCAL_PROVIDER_NAME:
        work_dir = agent.work_dir
        if work_dir.exists():
            branch = get_current_git_branch(work_dir, cg)
            if branch is not None:
                return branch
            logger.debug("Could not determine git branch for agent {} at {}", agent.name, work_dir)

    # Fallback: naming convention
    return f"mng/{agent.name}-{agent.host.provider_name}"


@pure
def _build_pr_branch_index(prs: tuple[PrInfo, ...]) -> dict[str, PrInfo]:
    """Build a lookup dict from branch name to the most relevant PR.

    If multiple PRs share the same branch, prefers OPEN > MERGED > CLOSED.
    """
    result: dict[str, PrInfo] = {}
    for pr in prs:
        existing = result.get(pr.head_branch)
        if existing is None or _pr_priority(pr) > _pr_priority(existing):
            result[pr.head_branch] = pr
    return result


@pure
def _pr_priority(pr: PrInfo) -> int:
    """Return priority for PR selection when multiple PRs share a branch.

    Higher value means higher priority. OPEN > MERGED > CLOSED.
    """
    if pr.state == PrState.OPEN:
        return 2
    if pr.state == PrState.MERGED:
        return 1
    return 0
