from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).parent.parent

PUBLISHABLE_PACKAGE_PYPROJECT_PATHS: Final[list[Path]] = [
    REPO_ROOT / "libs" / "mngr" / "pyproject.toml",
    REPO_ROOT / "libs" / "imbue_common" / "pyproject.toml",
    REPO_ROOT / "libs" / "concurrency_group" / "pyproject.toml",
]
