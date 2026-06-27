import subprocess
import sys
from pathlib import Path

import pytest

# Repo root — all CLI commands run from here so data/ is found correctly
REPO_ROOT = Path(__file__).parent.parent
ENERGY = [sys.executable, "-m", "eia.cli"]


def run(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run the energy CLI with the given subcommand and args."""
    return subprocess.run(
        ENERGY + list(args),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )
