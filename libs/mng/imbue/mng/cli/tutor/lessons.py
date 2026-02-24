from textwrap import dedent

from imbue.mng.cli.tutor.data_types import AgentExistsCheck
from imbue.mng.cli.tutor.data_types import AgentInStateCheck
from imbue.mng.cli.tutor.data_types import AgentNotExistsCheck
from imbue.mng.cli.tutor.data_types import FileExistsInAgentWorkDirCheck
from imbue.mng.cli.tutor.data_types import Lesson
from imbue.mng.cli.tutor.data_types import LessonStep
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName

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
            details=dedent("""\
                Connect to the agent with `mng connect agent-smith`, then ask it to
                create a file called `blue-pill.txt` and make a commit."""),
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
                expected_states=(AgentLifecycleState.STOPPED,),
            ),
        ),
        LessonStep(
            heading="Restart the agent",
            details=dedent("""\
                Run `mng start agent-smith` and then `mng connect agent-smith` to restart
                and reconnect to the agent. You can see all its work is still there."""),
            check=AgentInStateCheck(
                agent_name=AgentName("agent-smith"),
                expected_states=(AgentLifecycleState.RUNNING, AgentLifecycleState.WAITING),
            ),
        ),
        LessonStep(
            heading="Destroy the agent",
            details="Run `mng destroy agent-smith` or press Ctrl-Q from within the tmux session.",
            check=AgentNotExistsCheck(agent_name=AgentName("agent-smith")),
        ),
    ),
)


LESSON_REMOTE_AGENTS = Lesson(
    title="Remote Agents on Modal",
    description="Learn to launch and manage agents running on Modal's cloud infrastructure.",
    steps=(
        LessonStep(
            heading="Create a remote agent",
            details=dedent("""\
                cd into any git repo and run `mng create morpheus --in modal`.
                The --in modal flag tells mng to launch the agent on Modal instead of
                locally. This will take a bit longer as it builds a remote sandbox."""),
            check=AgentExistsCheck(agent_name=AgentName("morpheus")),
        ),
        LessonStep(
            heading="Make some changes using your remote agent",
            details=dedent("""\
                Connect to the agent with `mng connect morpheus`, then ask it to
                create a file called `red-pill.txt` and make a commit."""),
            check=FileExistsInAgentWorkDirCheck(
                agent_name=AgentName("morpheus"),
                file_path="red-pill.txt",
            ),
        ),
        LessonStep(
            heading="Stop the remote agent",
            details="Run `mng stop morpheus`, or press Ctrl-T from within the tmux session.",
            check=AgentInStateCheck(
                agent_name=AgentName("morpheus"),
                expected_states=(AgentLifecycleState.STOPPED,),
            ),
        ),
        LessonStep(
            heading="Restart the remote agent",
            details=dedent("""\
                Run `mng start morpheus` and then `mng connect morpheus` to restart
                and reconnect to the agent. You can see all its work is still there."""),
            check=AgentInStateCheck(
                agent_name=AgentName("morpheus"),
                expected_states=(AgentLifecycleState.RUNNING, AgentLifecycleState.WAITING),
            ),
        ),
        LessonStep(
            heading="Destroy the remote agent",
            details="Run `mng destroy morpheus` or press Ctrl-Q from within the tmux session.",
            check=AgentNotExistsCheck(agent_name=AgentName("morpheus")),
        ),
    ),
)


ALL_LESSONS: tuple[Lesson, ...] = (
    LESSON_GETTING_STARTED,
    LESSON_REMOTE_AGENTS,
)
