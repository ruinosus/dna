from __future__ import annotations

import tomllib
from pathlib import Path


def test_knowledge_tests_install_chonkie_directly_in_dev():
    pyproject = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text()
    )
    local_dev = pyproject["dependency-groups"]["dev"]
    package_dev = pyproject["project"]["optional-dependencies"]["dev"]

    assert any(dependency.startswith("chonkie") for dependency in local_dev)
    assert any(dependency.startswith("chonkie") for dependency in package_dev)
    assert "dna-sdk[knowledge]" not in package_dev