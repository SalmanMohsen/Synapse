import pytest
import os
import json
from unittest.mock import MagicMock, patch
from app.sandbox.container import SandboxHandle
from app.validation import validate_step_changes


@pytest.fixture
def mock_handle():
    handle = MagicMock(spec=SandboxHandle)
    handle.name = "test-sandbox"
    handle.repo_mount = "/workspace/repo"
    return handle


@pytest.mark.asyncio
async def test_validation_expected_action_type_no_changes(mock_handle):
    # Scenario: Agent reported changes completed but nothing was touched on disk
    success, check_tier, error = await validate_step_changes(
        handle=mock_handle,
        host_repo_path="/fake/path",
        touched_files=[],
        expected_action_type="modify"
    )

    assert success is False
    assert check_tier == "sanity_only"
    assert "Expected action type 'modify' but no file changes" in error


@pytest.mark.asyncio
@patch("app.validation.exec_in_sandbox")
@patch("os.path.isfile")
async def test_validation_tier1_makefile_success(mock_isfile, mock_exec, mock_handle):
    # Setup Makefile detection
    mock_isfile.side_effect = lambda path: path.endswith("Makefile") or path.endswith("touched.py")

    # Mock both make lint and make test passing cleanly
    mock_exec.side_effect = [
        (0, "Lint success"),
        (0, "Tests passed")
    ]

    success, check_tier, error = await validate_step_changes(
        handle=mock_handle,
        host_repo_path="/fake/path",
        touched_files=["touched.py"]
    )

    assert success is True
    assert check_tier == "repo_test_suite"
    assert error is None


@pytest.mark.asyncio
@patch("app.validation.exec_in_sandbox")
@patch("os.path.isfile")
async def test_validation_tier2_python_ruff_failures(mock_isfile, mock_exec, mock_handle):
    # Skip Tier 1 setup
    mock_isfile.side_effect = lambda path: path.endswith("touched.py")

    # Ruff execution simulation: check succeeds but formatting fails
    mock_exec.side_effect = [
        (0, "No issues found"),
        (1, "Incorrect formatting on line 12")
    ]

    success, check_tier, error = await validate_step_changes(
        handle=mock_handle,
        host_repo_path="/fake/path",
        touched_files=["touched.py"]
    )

    assert success is False
    assert check_tier == "generic_validator"
    assert "Ruff Format exit 1" in error


@pytest.mark.asyncio
@patch("os.path.isfile")
@patch("builtins.open")
async def test_validation_tier3_git_conflict_detection(mock_open, mock_isfile, mock_handle):
    # Mock file check for .txt file to bypass Tier 2 generic checks
    mock_isfile.side_effect = lambda path: path.endswith("touched.txt")

    # Mock reading a file containing unresolved git conflict markers
    mock_file = MagicMock()
    mock_file.read.return_value = "def add():\n<<<<<<< HEAD\n    return x + y\n=======\n    return y + x\n>>>>>>> dev"
    mock_open.return_value.__enter__.return_value = mock_file

    success, check_tier, error = await validate_step_changes(
        handle=mock_handle,
        host_repo_path="/fake/path",
        touched_files=["touched.txt"]
    )

    assert success is False
    assert check_tier == "sanity_only"
    assert "contains unresolved git conflict markers" in error