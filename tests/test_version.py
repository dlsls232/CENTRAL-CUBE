from __future__ import annotations

import re
import tomllib
from pathlib import Path

from central_cube import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_build_metadata() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    installer = (ROOT / "installer" / "CentralCube.iss").read_text(encoding="utf-8")
    match = re.search(r'#define MyAppVersion "([^"]+)"', installer)
    assert match is not None
    assert __version__ == project_version == match.group(1)


def test_readme_declares_current_version() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(f"# CENTRAL CUBE {__version__}")
