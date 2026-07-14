import logging
from app.schemas.plan import DevelopmentPlan, ActionType
from app.ingestion.qdrant_store import file_exists_in_chunks

logger = logging.getLogger(__name__)


class FileGroundingValidationError(Exception):
    """Exception raised when mechanical file-grounding validation fails."""
    def __init__(self, message: str, step_number: int | None = None, file_path: str | None = None):
        super().__init__(message)
        self.step_number = step_number
        self.file_path = file_path


async def validate_development_plan_grounding(project_id: str, plan: DevelopmentPlan) -> None:
    """Perform a mechanical validation check against Qdrant collection payloads.
    
    Rules:
    1. Every file targeted for 'modify' or 'delete' actions must exist in Qdrant's codebase index.
    2. Every file targeted for 'create' actions must NOT exist in Qdrant's codebase index.
    3. 'no_op' actions are skipped.
    
    If any check fails, raises FileGroundingValidationError.
    """
    for step in plan.steps:
        if step.action_type == ActionType.no_op:
            continue

        file_path = step.target_file_path.strip()
        if not file_path:
            raise FileGroundingValidationError(
                f"Step {step.step_number} has action '{step.action_type.value}' but target_file_path is empty.",
                step_number=step.step_number,
                file_path=file_path,
            )

        exists = await file_exists_in_chunks(project_id, file_path)

        if step.action_type in (ActionType.modify, ActionType.delete):
            if not exists:
                msg = (
                    f"File-grounding validation failed at Step {step.step_number}: "
                    f"Attempted to '{step.action_type.value}' file '{file_path}', "
                    f"but it does not exist in the codebase indexing."
                )
                logger.error(msg)
                raise FileGroundingValidationError(
                    msg,
                    step_number=step.step_number,
                    file_path=file_path,
                )

        elif step.action_type == ActionType.create:
            if exists:
                msg = (
                    f"File-grounding validation failed at Step {step.step_number}: "
                    f"Attempted to '{step.action_type.value}' file '{file_path}', "
                    f"but it already exists in the codebase indexing."
                )
                logger.error(msg)
                raise FileGroundingValidationError(
                    msg,
                    step_number=step.step_number,
                    file_path=file_path,
                )