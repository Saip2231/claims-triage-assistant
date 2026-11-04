"""Shared pytest fixtures that point at the copied sample data.

Each fixture skips (instead of erroring) when its file is missing, so the
message tells you exactly what to copy into claims_triage/sample_data/.
"""

from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Sample data missing: {path} (copy it in as described in Stage 0)")
    return path


@pytest.fixture(scope="session")
def sample_dir() -> Path:
    """The claims_triage/sample_data folder."""
    return _require(SAMPLE_DIR)


@pytest.fixture(scope="session")
def claims_dir() -> Path:
    """Folder holding the 10 sample claims in both PDF and TXT."""
    return _require(SAMPLE_DIR / "claims")


@pytest.fixture(scope="session")
def workbook_path() -> Path:
    """The reference workbook (claims_triage_dataset.xlsx)."""
    return _require(SAMPLE_DIR / "claims_triage_dataset.xlsx")


@pytest.fixture(scope="session")
def policy_path() -> Path:
    """The policy and guideline PDF."""
    return _require(SAMPLE_DIR / "policy_documents.pdf")
