"""Generate verify skill markdown files from vet's identification guides.

Requires a checkout of imbue-ai/vet. Pass the path via --vet-repo or VET_REPO env var.

Generated files (do not edit directly -- run this script to regenerate):
  .claude/skills/verify-conversation/categories.md
  .claude/skills/autofix/verify-and-fix.md

Usage:
    uv run python scripts/generate_verify_skills.py --vet-repo /path/to/vet
    VET_REPO=/path/to/vet uv run python scripts/generate_verify_skills.py
    uv run python scripts/generate_verify_skills.py --check
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SKILL_PATHS = {
    "conversation": REPO_ROOT / ".claude" / "skills" / "verify-conversation" / "categories.md",
    "verify-and-fix": REPO_ROOT / ".claude" / "skills" / "autofix" / "verify-and-fix.md",
}
PREAMBLE_PATHS = {
    "verify-and-fix": SCRIPT_DIR / "verify-and-fix-preamble.md",
}


# ---------------------------------------------------------------------------
# Formatting helpers (mirror generate_verify_md.py from vet)
# ---------------------------------------------------------------------------


def format_guide_section(guide) -> str:
    """Format a single IssueIdentificationGuide into a markdown section."""
    lines: list[str] = []

    lines.append(f"## {guide.issue_code.value}")
    lines.append("")

    lines.append(guide.guide)
    lines.append("")

    if guide.examples:
        lines.append("**Examples:**")
        for example in guide.examples:
            lines.append(f"- {example}")
        lines.append("")

    if guide.exceptions:
        lines.append("**Exceptions:**")
        for exception in guide.exceptions:
            lines.append(f"- {exception}")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Preambles and output formats
# ---------------------------------------------------------------------------

BRANCH_PREAMBLE = textwrap.dedent("""\
    # Issue Categories

    Review the code for the following types of issues:
""")

CONVERSATION_PREAMBLE = textwrap.dedent("""\
    # Issue Categories

    Review the conversation for the following types of issues:
""")

CONVERSATION_OUTPUT_FORMAT = textwrap.dedent("""\
    ## Output Format

    After your analysis when you are creating the final json file of issues, make a JSON record with each of the following fields (in order) for each issue you decide is valid to report, and append it as a new line to the final output json file:

    - issue_type: the issue type code from above (e.g., "misleading_behavior", "instruction_file_disobeyed", "instruction_to_save")
    - description: a complete description of the issue. Phrase it collaboratively rather than combatively -- the response will be given as feedback to the agent
    - confidence_reasoning: the thought process for how confident you are that it is an issue at all
    - confidence: a confidence score between 0.0 and 1.0 (1.0 = absolutely certain it is an issue, 0.0 = no confidence at all, should roughly be the probability that it is an actual issue to 1 decimal place)
    - severity_reasoning: the thought process for how severe the issue is (assuming it were an issue, i.e., ignoring confidence)
    - severity: one of "CRITICAL", "MAJOR", "MINOR", or "NITPICK", where
        - CRITICAL: must be addressed; the agent fundamentally failed to do what was asked or made a serious error
        - MAJOR: should be addressed; the agent missed something significant or made a meaningful mistake
        - MINOR: could be addressed; the agent's work has a minor gap or issue
        - NITPICK: optional; a very minor observation
""")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate_branch_markdown(vet_modules) -> str:
    """Generate branch issue categories: batched commit + correctness guides."""
    ISSUE_CODES_FOR_BATCHED_COMMIT_CHECK = vet_modules["ISSUE_CODES_FOR_BATCHED_COMMIT_CHECK"]
    ISSUE_CODES_FOR_CORRECTNESS_CHECK = vet_modules["ISSUE_CODES_FOR_CORRECTNESS_CHECK"]
    ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE = vet_modules["ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE"]

    # Deduplicate while preserving order.
    seen: set = set()
    codes = []
    for code in (*ISSUE_CODES_FOR_BATCHED_COMMIT_CHECK, *ISSUE_CODES_FOR_CORRECTNESS_CHECK):
        if code not in seen:
            seen.add(code)
            codes.append(code)

    guides = [ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE[code] for code in codes]

    sections: list[str] = [BRANCH_PREAMBLE]
    for guide in guides:
        sections.append(format_guide_section(guide))
    return "\n".join(sections)


def generate_conversation_markdown(vet_modules) -> str:
    """Generate categories.md: conversation history guides."""
    ISSUE_CODES_FOR_CONVERSATION_HISTORY_CHECK = vet_modules["ISSUE_CODES_FOR_CONVERSATION_HISTORY_CHECK"]
    ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE = vet_modules["ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE"]

    guides = [ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE[code] for code in ISSUE_CODES_FOR_CONVERSATION_HISTORY_CHECK]

    sections: list[str] = [CONVERSATION_PREAMBLE]
    for guide in guides:
        sections.append(format_guide_section(guide))
    sections.append(CONVERSATION_OUTPUT_FORMAT)
    return "\n".join(sections)


def generate_verify_and_fix_markdown(vet_modules) -> str:
    """Generate verify-and-fix.md: preamble + branch issue categories."""
    preamble = PREAMBLE_PATHS["verify-and-fix"].read_text()
    branch_categories = generate_branch_markdown(vet_modules)
    return preamble.rstrip() + "\n\n---\n\n" + branch_categories


MODES = {
    "conversation": generate_conversation_markdown,
    "verify-and-fix": generate_verify_and_fix_markdown,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_vet(vet_repo: Path) -> dict:
    """Import vet modules and return the symbols we need."""
    vet_str = str(vet_repo)
    if vet_str not in sys.path:
        sys.path.insert(0, vet_str)

    from vet.imbue_core.data_types import IssueCode
    from vet.issue_identifiers.identification_guides import ISSUE_CODES_FOR_BATCHED_COMMIT_CHECK
    from vet.issue_identifiers.identification_guides import ISSUE_CODES_FOR_CONVERSATION_HISTORY_CHECK
    from vet.issue_identifiers.identification_guides import ISSUE_CODES_FOR_CORRECTNESS_CHECK
    from vet.issue_identifiers.identification_guides import ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE

    return {
        "IssueCode": IssueCode,
        "ISSUE_CODES_FOR_BATCHED_COMMIT_CHECK": ISSUE_CODES_FOR_BATCHED_COMMIT_CHECK,
        "ISSUE_CODES_FOR_CORRECTNESS_CHECK": ISSUE_CODES_FOR_CORRECTNESS_CHECK,
        "ISSUE_CODES_FOR_CONVERSATION_HISTORY_CHECK": ISSUE_CODES_FOR_CONVERSATION_HISTORY_CHECK,
        "ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE": ISSUE_IDENTIFICATION_GUIDES_BY_ISSUE_CODE,
    }


def _resolve_vet_repo(explicit: Path | None) -> Path | None:
    """Resolve the vet repo path from explicit arg, env var, or default location."""
    if explicit is not None:
        return explicit
    env = os.environ.get("VET_REPO")
    if env:
        return Path(env)
    # Default fallback
    default = Path.home() / "vet"
    if (default / "vet").is_dir():
        return default
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate verify skill markdown from vet's identification guides.",
    )
    parser.add_argument(
        "--vet-repo",
        type=Path,
        default=None,
        help="Path to vet repo checkout. Falls back to VET_REPO env var, then ~/vet.",
    )
    parser.add_argument(
        "mode",
        choices=[*MODES.keys(), "all"],
        nargs="?",
        default="all",
        help="Which skill to generate (default: all).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that on-disk files match what would be generated. Exits non-zero if stale.",
    )
    args = parser.parse_args()

    vet_repo = _resolve_vet_repo(args.vet_repo)
    if vet_repo is None:
        parser.error("Could not find vet repo. Use --vet-repo, VET_REPO env var, or clone to ~/vet.")
    vet_repo = vet_repo.resolve()
    if not (vet_repo / "vet").is_dir():
        parser.error(f"Does not look like a vet checkout: {vet_repo}")

    vet_modules = load_vet(vet_repo)

    modes_to_run = MODES.keys() if args.mode == "all" else [args.mode]

    if args.check:
        ok = True
        for mode in modes_to_run:
            path = SKILL_PATHS[mode]
            expected = MODES[mode](vet_modules)
            if not path.exists():
                print(f"MISSING {path.relative_to(REPO_ROOT)}", file=sys.stderr)
                ok = False
            elif path.read_text() != expected:
                print(f"STALE   {path.relative_to(REPO_ROOT)}", file=sys.stderr)
                ok = False
            else:
                print(f"OK      {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        if ok:
            print("All generated files are up to date.", file=sys.stderr)
        else:
            print("Run without --check to regenerate.", file=sys.stderr)
            raise SystemExit(1)
        return

    for mode in modes_to_run:
        path = SKILL_PATHS[mode]
        content = MODES[mode](vet_modules)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text() if path.exists() else None
        if content != existing:
            path.write_text(content)
            print(f"Updated: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        else:
            print(f"OK:      {path.relative_to(REPO_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
