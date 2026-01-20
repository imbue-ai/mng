#!/usr/bin/env python3
"""Compiles Python examples from the style guide into a single test file."""

import re
from pathlib import Path

STYLE_GUIDE_PATH = Path(__file__).parent.parent / "style_guide.md"
OUTPUT_PATH = Path(__file__).parent / "style_guide.py"


def extract_python_blocks(markdown_content: str) -> list[str]:
    """Extract all Python code blocks from markdown."""
    pattern = r"```python\n(.*?)```"
    matches = re.findall(pattern, markdown_content, re.DOTALL)
    return matches


def strip_main_block(code: str) -> str:
    """Remove if __name__ == '__main__' blocks from code."""
    # Remove the if __name__ == "__main__": main() pattern
    code = re.sub(r'\nif __name__ == "__main__":\n    main\(\)\n?', "\n", code)
    code = re.sub(r"\nif __name__ == '__main__':\n    main\(\)\n?", "\n", code)
    return code


def filter_todo_app_imports(code: str) -> str:
    """Remove imports from todo_app.* since objects should already be defined."""
    lines = code.split("\n")
    filtered_lines = [line for line in lines if not line.strip().startswith("from todo_app")]
    return "\n".join(filtered_lines)


def remove_skip_decorators(code: str) -> str:
    """Remove pytest.mark.skip decorators."""
    # Remove @pytest.mark.skip(...) lines
    code = re.sub(r"@pytest\.mark\.skip\([^)]*\)\n", "", code)
    return code


def extract_imports(code: str) -> tuple[list[str], str]:
    """Extract import statements from code and return (imports, code_without_imports)."""
    lines = code.split("\n")
    import_lines = []
    code_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            import_lines.append(line)
        else:
            code_lines.append(line)

    return import_lines, "\n".join(code_lines)


def main() -> None:
    markdown_content = STYLE_GUIDE_PATH.read_text()
    python_blocks = extract_python_blocks(markdown_content)

    # Collect all imports from all blocks
    all_imports: list[str] = []
    processed_blocks: list[tuple[int, str]] = []

    for i, block in enumerate(python_blocks):
        processed_block = strip_main_block(block)
        processed_block = filter_todo_app_imports(processed_block)
        processed_block = remove_skip_decorators(processed_block)

        # Extract imports and code separately
        imports, code = extract_imports(processed_block)
        all_imports.extend(imports)

        # Only add non-empty code blocks
        if code.strip():
            processed_blocks.append((i + 1, code))

    # Remove duplicate imports while preserving order
    seen_imports = set()
    unique_imports = []
    for imp in all_imports:
        if imp not in seen_imports:
            seen_imports.add(imp)
            unique_imports.append(imp)

    # Build final code with minimal stubs for forward references
    combined_code = "# ruff: noqa: F811, E501, F401, I001, F841, ARG001, ERA001\n"
    combined_code += "from __future__ import annotations\n\n"
    combined_code += "\n".join(unique_imports)
    combined_code += "\n\n"

    for block_idx, code in processed_blocks:
        combined_code += f"# === Example block {block_idx} ===\n"
        combined_code += code
        combined_code += "\n\n"

    OUTPUT_PATH.write_text(combined_code)
    print(f"Compiled {len(python_blocks)} Python blocks to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
