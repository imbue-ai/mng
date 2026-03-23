"""Basic end-to-end tests for the mng CLI.

These tests exercise mng through its CLI interface via subprocess. The e2e
fixture configures a custom connect_command that records tmux sessions via
asciinema instead of attaching interactively.
"""

import json

import pytest

from imbue.mng.e2e.conftest import E2eSession
from imbue.skitwright.expect import expect


@pytest.mark.release
def test_help_succeeds(e2e: E2eSession) -> None:
    e2e.write_tutorial_block("""
    # or see the other commands--list, destroy, message, connect, push, pull, clone, and more!  These other commands are covered in their own sections below.
    mng --help
    """)
    result = e2e.run(
        "mng --help",
        comment="or see the other commands--list, destroy, message, connect, push, pull, clone, and more!",
    )
    expect(result).to_succeed()
    expect(result.stdout).to_contain("Usage")
    expect(result.stdout).to_contain("create")
    expect(result.stdout).to_contain("list")


@pytest.mark.release
def test_create_help_succeeds(e2e: E2eSession) -> None:
    e2e.write_tutorial_block("""
    # tons more arguments for anything you could want! As always, you can learn more via --help
    mng create --help
    """)
    result = e2e.run(
        "mng create --help",
        comment="tons more arguments for anything you could want! As always, you can learn more via --help",
    )
    expect(result).to_succeed()
    expect(result.stdout).to_contain("--no-connect")
    expect(result.stdout).to_contain("--command")


@pytest.mark.release
def test_list_with_no_agents(e2e: E2eSession) -> None:
    result = e2e.run("mng list", comment="List agents in a fresh environment")
    expect(result).to_succeed()
    expect(result.stdout).to_contain("No agents found")


@pytest.mark.release
def test_list_json_with_no_agents(e2e: E2eSession) -> None:
    result = e2e.run("mng list --format json", comment="List agents as JSON in a fresh environment")
    expect(result).to_succeed()
    parsed = json.loads(result.stdout)
    assert parsed["agents"] == []


@pytest.mark.release
@pytest.mark.tmux
def test_create_named_agent(e2e: E2eSession) -> None:
    e2e.write_tutorial_block("""
    # when creating agents to accomplish tasks, it's recommended that you give them a name to make it easier to manage them:
    mng create my-task
    # that command give the agent a name of "my-task". If you don't specify a name, mng will generate a random one for you.
    """)
    expect(
        e2e.run(
            "mng create my-task --command 'sleep 99999' --no-ensure-clean",
            comment="when creating agents to accomplish tasks, it's recommended that you give them a name",
        )
    ).to_succeed()

    list_result = e2e.run("mng list", comment="Verify agent appears in list")
    expect(list_result).to_succeed()
    expect(list_result.stdout).to_match(r"my-task\s+(RUNNING|WAITING)")


@pytest.mark.release
@pytest.mark.tmux
def test_create_with_json_output(e2e: E2eSession) -> None:
    e2e.write_tutorial_block("""
    # you can control output format for scripting:
    mng create my-task --no-connect --format json
    # (--quiet suppresses all output)
    """)
    create_result = e2e.run(
        "mng create my-task --no-connect --command 'sleep 99999' --no-ensure-clean --format json",
        comment="you can control output format for scripting",
    )
    expect(create_result).to_succeed()

    # The create command with --format json should output valid JSON with agent_id and host_id
    create_parsed = json.loads(create_result.stdout)
    assert "agent_id" in create_parsed
    assert "host_id" in create_parsed

    # Verify the agent appears in the list with correct details
    list_result = e2e.run("mng list --format json", comment="Verify agent appears in JSON list")
    expect(list_result).to_succeed()
    parsed = json.loads(list_result.stdout)
    assert len(parsed["agents"]) == 1
    agent = parsed["agents"][0]
    assert agent["name"] == "my-task"
    assert agent["state"] in ("RUNNING", "WAITING")


@pytest.mark.release
@pytest.mark.tmux
def test_create_with_quiet_output(e2e: E2eSession) -> None:
    e2e.write_tutorial_block("""
    # you can control output format for scripting:
    mng create my-task --no-connect --format json
    # (--quiet suppresses all output)
    """)
    create_result = e2e.run(
        "mng create my-task --no-connect --command 'sleep 99999' --no-ensure-clean --quiet",
        comment="--quiet suppresses all output",
    )
    expect(create_result).to_succeed()
    expect(create_result.stdout).to_be_empty()

    # Verify the agent was still created despite quiet output
    list_result = e2e.run("mng list --format json", comment="Verify agent was created")
    expect(list_result).to_succeed()
    parsed = json.loads(list_result.stdout)
    assert len(parsed["agents"]) == 1
    assert parsed["agents"][0]["name"] == "my-task"


@pytest.mark.release
@pytest.mark.tmux
def test_create_headless(e2e: E2eSession) -> None:
    e2e.write_tutorial_block("""
    # mng is very much meant to be used for scripting and automation, so nothing requires interactivity.
    # if you want to be sure that interactivity is disabled, you can use the --headless flag:
    mng create my-task --headless
    """)
    expect(
        e2e.run(
            "mng create my-task --command 'sleep 99999' --no-ensure-clean --headless",
            comment="if you want to be sure that interactivity is disabled, you can use the --headless flag",
        )
    ).to_succeed()

    list_result = e2e.run("mng list", comment="Verify headless agent appears in list")
    expect(list_result).to_succeed()
    expect(list_result.stdout).to_contain("my-task")


@pytest.mark.release
@pytest.mark.tmux
def test_create_and_destroy_agent(e2e: E2eSession) -> None:
    expect(
        e2e.run(
            "mng create my-task --command 'sleep 99999' --no-ensure-clean",
            comment="Create agent to be destroyed",
        )
    ).to_succeed()

    destroy_result = e2e.run("mng destroy my-task --force", comment="Destroy the agent")
    expect(destroy_result).to_succeed()

    list_result = e2e.run("mng list", comment="Verify agent no longer appears in list")
    expect(list_result).to_succeed()
    expect(list_result.stdout).not_to_contain("my-task")


@pytest.mark.release
@pytest.mark.tmux
def test_create_and_rename_agent(e2e: E2eSession) -> None:
    expect(
        e2e.run(
            "mng create my-task --command 'sleep 99999' --no-ensure-clean",
            comment="Create agent to be renamed",
        )
    ).to_succeed()

    rename_result = e2e.run(
        "mng rename my-task renamed-task",
        comment="Rename agent to renamed-task",
    )
    expect(rename_result).to_succeed()

    list_result = e2e.run("mng list", comment="Verify only the new name appears")
    expect(list_result).to_succeed()
    expect(list_result.stdout).to_contain("renamed-task")
    expect(list_result.stdout).not_to_contain("my-task")


@pytest.mark.release
@pytest.mark.tmux
def test_create_with_label(e2e: E2eSession) -> None:
    e2e.write_tutorial_block("""
    # you can add labels to organize your agents and tags for host metadata:
    mng create my-task --label team=backend --host-label env=staging
    """)
    expect(
        e2e.run(
            "mng create my-task --command 'sleep 99999' --no-ensure-clean --label team=backend --host-label env=staging",
            comment="you can add labels to organize your agents and tags for host metadata",
        )
    ).to_succeed()

    list_result = e2e.run("mng list --format json", comment="Verify label appears in JSON output")
    expect(list_result).to_succeed()
    parsed = json.loads(list_result.stdout)
    agents = parsed["agents"]
    matching_agents = [a for a in agents if a["name"] == "my-task"]
    assert len(matching_agents) == 1
    assert matching_agents[0]["labels"]["team"] == "backend"
