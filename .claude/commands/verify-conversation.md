---
allowed-tools: Bash:*
description: Review a conversation transcript for errors, missed requirements, and quality issues.
---

# Conversation Review Guide

This command reviews a conversation transcript to identify issues with the agent's work, without examining the diff directly.

## Instructions

### 1. Set Up

First, determine your reviewer window name and clean up old review files:

```bash
./scripts/cleanup_review_files.sh
```

Then determine your window name (you'll need this for file paths later):

```bash
WINDOW=$(tmux display-message -t "$TMUX_PANE" -p '#W' 2>/dev/null || echo reviewer_0) && echo "$WINDOW"
```

### 2. Read the Conversation

Get the conversation transcript by running:

```bash
./scripts/print_review_transcript.sh
```

If the output is empty, there is no conversation to review -- state this and exit.

### 3. Create Initial Issue List

Go through the conversation and create a comprehensive list of ALL potential issues you notice, using the issue categories below. Be thorough at this stage -- it's better to identify more potential issues initially than to miss something.

Do not flag:
- Stylistic choices in the conversation itself (how the agent communicates)
- Issues that the agent identified and fixed during the conversation
- Minor formatting or communication preferences

For each potential issue, note:
- The issue type (from the categories below)
- A brief description of what you observed

Put these observations into the "initial issues file" for tracking:

    .reviews/initial_issue_list/$WINDOW.md

### 4. Analyze Each Potential Issue

After creating the initial list in that file, read that file, and, for each issue in that initial list:

1. Think carefully about each of the following:
- Is this actually a problem, or is it acceptable given the context?
- Does it fall under any of the exceptions listed for that issue type?
- Could you be misreading the conversation? Is there context you might be missing?
- How severe is it? (CRITICAL / MAJOR / MINOR / NITPICK)
2. If it is a problem (that has not already been output), output the issue by appending to the "final output json file" with all the required details, in order (one JSON object per line, i.e. one issue per line, see exact output format details below)

The "final output json file" is:

    .reviews/final_issue_json/$WINDOW.json

When finished with all issues, touch the done marker:

    .reviews/final_issue_json/$WINDOW.json.done

---

## Issue Categories

Review the conversation for the following types of issues:

### misleading_behavior

The agent did something misleading in the conversation history.

When writing your response, phrase it collaboratively rather than combatively. The response will be given as feedback to the agent, so it should avoid making the agent defensive by assuming good intentions when possible. The collaborative tone shouldn't make you more lenient -- you should not hesitate to point out behavior that might mislead the user.

However, if the agent did something misleading, but then corrected its mistake, such that the final result shown to the user was not misleading, you should not point out the original mistake. You should also not point out the behavior if the user is clearly aware of it; for example, you should not flag misleading behavior if the user asked the agent to mark something as done when it was not.

Also do not flag all behavior that doesn't match the user's request as misleading; for example, you should not flag misleading behavior if the agent makes changes the user didn't ask for, but the changes aren't themselves misleading, like a refactoring that improves the code.

In addition, you should not consider checking off tasks on the TODO list as potentially misleading; the agent is intended to check off a TODO whenever it is done considering the task for that turn, which may be because it has not completed the task but needs more information to proceed.

When writing the description, you don't need to explain why the behavior was misleading -- just describe the behavior itself.

Any self-identification made by the agent in the conversation history should be assumed to be accurate.

**Examples:**
- The agent can't run a test file, so it checks that the test file has valid syntax instead, and proceeds as though the tests passed.
- The agent claims in a message to have achieved its original goal when it clearly has not.
- The agent uses fake data when it is unable to get real data, e.g. as a 'fallback'.

---

### incorrect_claim

The agent stated something that appears to be factually wrong based on the conversation context. This is distinct from misleading_behavior -- here the agent may genuinely believe what it is saying, but it is incorrect.

**Examples:**
- The agent claims tests passed when the conversation shows they failed.
- The agent says a file contains certain code, but the file contents shown in the conversation indicate otherwise.
- The agent asserts that a function exists or behaves a certain way when the codebase evidence contradicts this.
- The agent incorrectly describes what a piece of code does.

**Exceptions:**
- Do not flag claims that are ambiguous or where there is not enough context in the conversation to determine correctness.
- Do not flag minor imprecisions in language that do not affect the outcome.

---

### unfulfilled_request

The user asked for something that wasn't done, was only partially done, or was done incorrectly.

**Examples:**
- The user asked for changes to multiple files but only some were modified.
- The user asked for a feature but the agent only implemented part of it.
- The user asked a question but the agent did not answer it or answered a different question.

**Exceptions:**
- If the agent explicitly acknowledged it could not complete part of the request and explained why, this is not an unfulfilled request.
- If the user changed their mind or redirected the agent during the conversation, the original request is superseded.

---

### reasoning_error

The agent made a logical error in its analysis, approach, or conclusions.

**Examples:**
- The agent misdiagnosed the root cause of a bug based on the evidence available in the conversation.
- The agent chose an approach that is clearly wrong given the constraints it identified.
- The agent drew an incorrect conclusion from code it read.

**Exceptions:**
- Do not flag suboptimal approaches as reasoning errors -- only flag cases where the reasoning is clearly wrong, not just where a better approach exists.

---

### incomplete_verification

The agent didn't run tests, didn't verify its work, or skipped verification steps that the project requires.

**Examples:**
- The project's CLAUDE.md requires running all tests after changes, but the agent only ran a subset.
- The agent made changes but never verified they work.
- The agent skipped manual verification of an interactive feature.

**Exceptions:**
- If the user explicitly told the agent to skip verification, this is not an issue.
- If the agent was unable to run tests due to environment issues and clearly communicated this, reduce severity.

---

### quality_concern

The agent's stated approach has obvious problems visible from the conversation alone, without needing to examine the diff.

**Examples:**
- The agent reimplemented something that clearly already exists in the codebase (based on conversation context).
- The agent discussed edge cases but then ignored them in its approach.
- The agent chose to write custom code when it acknowledged a library exists for the purpose.

**Exceptions:**
- Do not flag quality concerns that require examining the actual code to verify -- this review is conversation-only.

---

### contradiction

The agent said one thing and then did or said something contradictory later in the conversation.

**Examples:**
- The agent said it would take approach A, then implemented approach B without explanation.
- The agent identified a requirement, then produced a solution that violates that requirement.
- The agent said a change was unnecessary, then made that change anyway.

**Exceptions:**
- If the agent explicitly acknowledged changing course and explained why, this is not a contradiction.
- If the user redirected the agent between the two statements, the earlier statement is superseded.

---

### unrequested_action

The agent made changes or took actions that the user did not ask for.

**Examples:**
- The agent refactored unrelated code that the user didn't ask to be changed.
- The agent added features, options, or configuration beyond what was requested.
- The agent modified test thresholds, coverage settings, or other constraints without being asked.
- The agent committed code when the user didn't ask it to commit.

**Exceptions:**
- Minor refactors directly related to the requested changes are acceptable.
- If the agent explained the additional changes and the user did not object, reduce severity.
- Actions that are clearly required by instruction files (e.g. CLAUDE.md says to always run tests) are not unrequested even if the user didn't explicitly ask for them.

---

### instruction_file_disobeyed

Explicit instructions in files such as .claude.md, CLAUDE.md, and AGENTS.md MUST be obeyed.

**Examples:**
- CLAUDE.md requests the use of single quotes only, but double quotes are used.
- AGENTS.md requests that new versions be created on every database update, but a database entry is modified directly.
- .claude.md says to always run the tests after making changes, but the agent did not run the tests.

**Exceptions:**
- Instructions in the closest file _above_ a location take precedence. For example, when considering a file foo/bar.py, foo/CLAUDE.md takes precedence over CLAUDE.md.
- Instructions only apply to the subtree below the file. For example, when considering a file foo/bar.py, foo/baz/CLAUDE.md does not apply.
- Applicable instructions should ONLY be contravened in the case of explicit user request -- but if the user does explicitly request something counter to the instruction files, this should not be reported as a disobeyed instruction file.

---

### instruction_to_save

The user gives guidance or feedback to the agent about general code style, their intent for the project, or anything else that is relevant beyond the scope of the current task.

**Examples:**
- The user tells the agent to move all the imports to the top of the file, and there is no preexisting instruction in the instruction file to have all imports at the top.
- The user asks the agent to avoid importing a library because they need image builds to be fast, and the project specification does not already mention that the application will run in a container under conditions where speed of builds could be reasonably considered to be a priority.
- The user provides an instruction that contradicts something in an AGENTS.md file.

---

## Output Format

After your analysis when you are creating the final json file of issues, make a JSON record with each of the following fields (in order) for each issue you decide is valid to report, and append it as a new line to the final output json file:

- issue_type: the issue type code from above (e.g. "misleading_behavior", "incorrect_claim", "unfulfilled_request", "reasoning_error", "incomplete_verification", "quality_concern", "contradiction", "unrequested_action", "instruction_file_disobeyed", "instruction_to_save")
- description: a complete description of the problem, including what the user asked for, what the agent did or said, and why it's an issue
- confidence_reasoning: the thought process for how confident you are that it is an issue at all
- confidence: a confidence score between 0.0 and 1.0 (1.0 = absolutely certain it is an issue, 0.0 = no confidence at all, should roughly be the probability that it is an actual issue to 1 decimal place)
- severity_reasoning: the thought process for how severe the issue is (assuming it were an issue, i.e., ignoring confidence)
- severity: one of "CRITICAL", "MAJOR", "MINOR", or "NITPICK", where
    - CRITICAL: must be addressed; the agent fundamentally failed to do what was asked or made a serious error
    - MAJOR: should be addressed; the agent missed something significant or made a meaningful mistake
    - MINOR: could be addressed; the agent's work has a minor gap or issue
    - NITPICK: optional; a very minor observation
