"""
pytest configuration: add the sidecar root to sys.path so that
metadata, stats, and export can be imported without a package install.
Provides session-scoped path fixtures pointing to the pre-generated
.mf4 files in tests/fixtures/.
"""
from __future__ import annotations

import os
import sys

import pytest

# Make sibling sidecar modules importable (metadata, stats, export, …)
SIDECAR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SIDECAR_ROOT not in sys.path:
    sys.path.insert(0, SIDECAR_ROOT)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


# --------------------------------------------------------------------------- #
# Session-scoped path fixtures — skip if the file hasn't been generated yet
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="session")
def minimal_mf4():
    path = _fixture_path("minimal.mf4")
    if not os.path.isfile(path):
        pytest.skip(f"fixture not found: {path} — run tests/generate_fixtures.py first")
    return path


@pytest.fixture(scope="session")
def bus_raw_mf4():
    path = _fixture_path("bus_raw.mf4")
    if not os.path.isfile(path):
        pytest.skip(f"fixture not found: {path} — run tests/generate_fixtures.py first")
    return path


@pytest.fixture(scope="session")
def multi_group_mf4():
    path = _fixture_path("multi_group.mf4")
    if not os.path.isfile(path):
        pytest.skip(f"fixture not found: {path} — run tests/generate_fixtures.py first")
    return path
