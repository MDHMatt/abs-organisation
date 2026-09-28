"""Run the complete repository quality gate."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    """Run one gate command from the repository root."""
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    """Run every local check in fail-fast order."""
    python = sys.executable
    run(python, "-m", "ruff", "check", ".")
    run(python, "-m", "ruff", "format", "--check", ".")
    run(python, "-m", "compileall", "-q", "absorg", "tests")
    run(python, "-m", "pytest", "-q")
    run(python, "-m", "build", "--no-isolation")

    npm_name = "npm.cmd" if os.name == "nt" else "npm"
    npm = shutil.which(npm_name)
    if npm is None:
        raise RuntimeError("npm is required for Markdown checks")
    run(npm, "ci")
    run(npm, "run", "lint:markdown")


if __name__ == "__main__":
    main()
