import pytest
from unittest.mock import patch
from app.schemas.plan import DevelopmentPlan, PlanStep, ActionType
from app.agent.validation import validate_development_plan_grounding, FileGroundingValidationError

@pytest.mark.asyncio
@patch("app.agent.validation.file_exists_in_chunks")
async def test_validate_development_plan_grounding_success(mock_file_exists):
    # Mocking file presence lookup inside index
    def file_exists_mock(project_id, path):
        existing_files = {"existing_file.py", "to_delete.py"}
        return path in existing_files
    mock_file_exists.side_effect = file_exists_mock

    plan = DevelopmentPlan(
        summary="Plan is validated successfully.",
        steps=[
            PlanStep(
                step_number=1,
                description="Modify existing file",
                action_type=ActionType.modify,
                target_file_path="existing_file.py",
                explanation="Modifying this class."
            ),
            PlanStep(
                step_number=2,
                description="Create a new endpoint",
                action_type=ActionType.create,
                target_file_path="new_file.py",  # Does not exist inside mock -> success
                explanation="Creating new class."
            ),
            PlanStep(
                step_number=3,
                description="Delete legacy file",
                action_type=ActionType.delete,
                target_file_path="to_delete.py",
                explanation="Deleting obsolete module."
            ),
            PlanStep(
                step_number=4,
                description="Run pytests to confirm validation pass",
                action_type=ActionType.no_op,
                target_file_path="N/A",
                explanation="Confirmation test."
            )
        ],
        affected_files=["existing_file.py", "new_file.py", "to_delete.py"]
    )

    # Should run and return cleanly without throwing exceptions
    await validate_development_plan_grounding("project-1", plan)


@pytest.mark.asyncio
@patch("app.agent.validation.file_exists_in_chunks")
async def test_validate_development_plan_grounding_modify_missing_file_fails(mock_file_exists):
    mock_file_exists.return_value = False # File does not exist inside repository

    plan = DevelopmentPlan(
        summary="Failing modify test.",
        steps=[
            PlanStep(
                step_number=1,
                description="Modify a missing core file",
                action_type=ActionType.modify,
                target_file_path="missing_core.py",
                explanation="Trying to modify a non-existent file."
            )
        ],
        affected_files=["missing_core.py"]
    )

    with pytest.raises(FileGroundingValidationError) as exc_info:
        await validate_development_plan_grounding("project-1", plan)
    assert exc_info.value.step_number == 1
    assert "missing_core.py" in str(exc_info.value)


@pytest.mark.asyncio
@patch("app.agent.validation.file_exists_in_chunks")
async def test_validate_development_plan_grounding_create_duplicate_file_fails(mock_file_exists):
    mock_file_exists.return_value = True # File already exists in repo

    plan = DevelopmentPlan(
        summary="Failing create test.",
        steps=[
            PlanStep(
                step_number=1,
                description="Create file that already exists",
                action_type=ActionType.create,
                target_file_path="existing_class.py",
                explanation="Accidental overlap."
            )
        ],
        affected_files=["existing_class.py"]
    )

    with pytest.raises(FileGroundingValidationError) as exc_info:
        await validate_development_plan_grounding("project-1", plan)
    assert exc_info.value.step_number == 1
    assert "already exists in the codebase" in str(exc_info.value)