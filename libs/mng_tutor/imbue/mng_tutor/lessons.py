from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng_tutor.data_types import AgentExistsCheck
from imbue.mng_tutor.data_types import AgentInStateCheck
from imbue.mng_tutor.data_types import AgentNotExistsCheck
from imbue.mng_tutor.data_types import FileExistsInAgentWorkDirCheck
from imbue.mng_tutor.data_types import Lesson
from imbue.mng_tutor.data_types import LessonStep

LESSON_GETTING_STARTED = Lesson(
    title="Getting Started",
    description="Learn to create, use, and manage your first agent.",
    steps=(
        LessonStep(
            heading="Create your first agent",
            details="cd into any git repo that you have, and run `mng create agent-smith` from there.",
            check=AgentExistsCheck(agent_name=AgentName("agent-smith")),
        ),
        LessonStep(
            heading="Make some changes using your agent",
            details=(
                "Connect to the agent with `mng connect agent-smith`, then ask it to\n"
                "create a file called `blue-pill.txt` and make a commit."
            ),
            check=FileExistsInAgentWorkDirCheck(
                agent_name=AgentName("agent-smith"),
                file_path="blue-pill.txt",
            ),
        ),
        LessonStep(
            heading="Stop the agent",
            details="Run `mng stop agent-smith`, or press Ctrl-T from within the tmux session.",
            check=AgentInStateCheck(
                agent_name=AgentName("agent-smith"),
                expected_state=AgentLifecycleState.STOPPED,
            ),
        ),
        LessonStep(
            heading="Restart the agent",
            details=(
                "Run `mng start agent-smith` and then `mng connect agent-smith` to restart\n"
                "and reconnect to the agent. You can see all its work is still there."
            ),
            check=AgentInStateCheck(
                agent_name=AgentName("agent-smith"),
                expected_state=AgentLifecycleState.RUNNING,
            ),
        ),
        LessonStep(
            heading="Destroy the agent",
            details="Run `mng destroy agent-smith` or press Ctrl-Q from within the tmux session.",
            check=AgentNotExistsCheck(agent_name=AgentName("agent-smith")),
        ),
    ),
)


LESSON_MANAGING_MULTIPLE_AGENTS = Lesson(
    title="Managing Multiple Agents",
    description="Practice creating and managing multiple agents at once.",
    steps=(
        LessonStep(
            heading="Create agent neo",
            details="cd into any git repo and run `mng create neo`.",
            check=AgentExistsCheck(agent_name=AgentName("neo")),
        ),
        LessonStep(
            heading="Create agent trinity",
            details="From the same or a different git repo, run `mng create trinity`.",
            check=AgentExistsCheck(agent_name=AgentName("trinity")),
        ),
        LessonStep(
            heading="Stop agent neo",
            details="Run `mng stop neo` to stop the first agent.",
            check=AgentInStateCheck(
                agent_name=AgentName("neo"),
                expected_state=AgentLifecycleState.STOPPED,
            ),
        ),
        LessonStep(
            heading="Destroy agent neo",
            details="Run `mng destroy neo` to permanently remove it.",
            check=AgentNotExistsCheck(agent_name=AgentName("neo")),
        ),
        LessonStep(
            heading="Destroy agent trinity",
            details="Run `mng destroy trinity` to clean up the last agent.",
            check=AgentNotExistsCheck(agent_name=AgentName("trinity")),
        ),
    ),
)


ALL_LESSONS: tuple[Lesson, ...] = (
    LESSON_GETTING_STARTED,
    LESSON_MANAGING_MULTIPLE_AGENTS,
)
