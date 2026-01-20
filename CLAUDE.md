IT IS CRITICAL TO FOLLOW ALL INSTRUCTIONS IN THIS FILE DURING YOUR WORK ON THIS PROJECT.

IF YOU FAIL TO FOLLOW ONE, YOU MUST EXPLICITLY CALL THAT OUT IN YOUR RESPONSE.

# Important things to know:

- This is a monorepo.
- ALWAYS run commands by calling "uv run" from the root of the git checkout (ex: "uv run mngr create ..."). Do NOT call "mngr" directly (it will refer to the wrong version).

# How to get started on any task:

Always begin your session by reading all documentation in the docs/ directory of the project you are working on. These represent *user-facing* documentation and are the most important to understand.

Next, ensure you have read all `.md` files immediately within the `specs/` folder. There's no need to read anything from subfolders of `specs/`, *except* for the particular spec that you will be working on. 

Once you've read these once during a session, there's no need to re-read them unless explicitly instructed to do so.

If you will be writing code, be sure to read the style_guide.md for the project. Then read all README.md files in the relevant project directories, as well as all `.py` files at the root of the project you are working on (ex: `primitives.py`, etc.). Also read everything in data_types, interfaces, and utils to ensure you understand the core abstractions.

Then take a look at the other code directories, and based on the task, determine which files are most relevant to read in depth. Be sure to read the full contents from those files.

Do NOT read files that end with "_test.py" during this first pass as they contain unit tests (unless you are explicitly instructed to read the unit tests).

Do NOT read files that start with "test_" either, as they contain integration, acceptance, and release tests (again, unless you are explicitly instructed to read the existing tests).

Only after doing all of the above should you begin writing code.

# Important commands and conventions:

- Never run `uv sync`, always run `uv sync --all-packages` instead

# Always remember these guidelines:

- Never misrepresent your progress. It is far better to say "I made some progress but didn't finish" than to say "I finished" when you did not.
- Always finish your response by using ultrathink to reflect on your work and identify any potential issues.
- If I ask for something that seems misguided, flag that immediately. Then attempt to do whatever makes the most sense given the request, and in your final reflection, be sure to flag that you had to diverge from the request and explain why.
- During your final reflection, if you see a potentially better way to do something (e.g. by using an existing library or reusing existing code), flag that as a potential task for future improvement.
- Never use emojis. Remove any emojis you see in the code or docs whenever you are modifying that code or those docs.
- Be concise in your communications. Don't hype up your results, say "perfect!", or use emojis. Be serious and professional.

# When coding, follow these guidelines:

- Only make the changes that are necessary for the current task.
- Before implementing something, check if there is something in the codebase or look for a library
- Reuse code and use external dependencies heavily. Before implementing something, make sure that it doesn't already exist in the codebase, and consider if there's a library that can be imported instead of implementing it yourself. We want to be able to maintain the minimum amount of code that gets the job done, even if that means introducing dependencies. If you don't know of a library but think one might be plausible, search the web. (I'm even open to using random GitHub projects, but run anything that's not a well-established library by me first so I can check if it's likely to be reliable.)
- Code quality is extremely important. Do not compromise on quality to deliver a result--if you don't know a good way to do something, ask.
- Follow the style guide!
- Use the power of the type system to constrain your code and provide some assurance of correctness. If some required property can't be guaranteed by the type system, it should be runtime checked (i.e. explode if it fails).
- You may write inline imports during your first pass, but during your reflection, be sure to go back and move any *that you created* to the top of the file instead.
- Avoid using the `TYPE_CHECKING` guard. Do not add it to files that do not already contain it, and never put imports inside of it yourself--you MUST ask for explicit permission to do this (it's generally a sign of bad architecture that should be fixed some other way).
- Do NOT write code in `__init__.py`--leave them completely blank (the only exception is for a line like "hookimpl = pluggy.HookimplMarker("mngr")", which should go at the very root __init__.py of a library).
- Do NOT make constructs like module-level usage of `__all__`
- Before finishing your response, ensure that you have run ALL tests in the project(s) you modified, and that they all pass. DO NOT just run a subset of the tests!
- Use this command **from the root of the git checkout** to run all tests: "uv run pytest". Never change directories to run tests! Just run the command from the root of the git checkout.
- **Never change diretories**. It's just a good way to get yourself confused.
- To help verify that you ran the tests, report the exact command you used to run the tests, as well as the total number of tests that passed and failed (and the number that failed had better be 0).
- If tests fail because of a lack of coverage, you should add tests for the new code that you wrote.
- If you see a flaky test, YOU MUST HIGHLIGHT THIS IN YOUR RESPONSE. Flaky tests must be fixed as soon as possible. Ideally you should finish your task, then if you are allowed to commit, commit, and try to fix the flaky test in a separate commit.
- To reiterate: code correctness and quality is the most important concern when writing code.

If desired, the user will explicitly instruct you not to commit.

By default, or if instructed to commit:
- Commit frequently and in general use git operations to your advantage (e.g. by reverting commits rather than manually undoing changes).
- Commit with a sensible commit message when you finish your response.
- Be sure to add any files you made before committing. This includes specs (.md files), configs, etc.!
- Even when writing specs, you should commit (if not explicitly instructed not to).

If instructed not to commit:
- do not commit anything! Simply leave the git state as it is at the end of your response.
- NEVER run git commands like git reset, git checkout, etc that might change the git state (when instructed not to commit you are collaborating with others in the same directory, so should not change other files or the git state).

# Silly error workarounds

If you get a failure in `test_no_type_errors` that seems spurious, try running `uv sync --all-packages` and then re-running the tests. If that doesn't work, the error is probably real, and should be fixed.

If you get a failure when trying to commit the first time, just try committing again (the pre-commit hook returns a non-zero exit code when ruff reformats files).
