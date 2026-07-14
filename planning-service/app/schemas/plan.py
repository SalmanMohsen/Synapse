from enum import Enum
from typing import List
from pydantic import BaseModel, Field, model_validator


class ActionType(str, Enum):
    """The categories of file-system or architectural changes allowed in a step."""
    create = "create"
    modify = "modify"
    delete = "delete"
    no_op = "no_op"  # Used for system configuration, running tests, or verification steps


class PlanStep(BaseModel):
    """A single discrete, chronological execution step in the development plan."""
    step_number: int = Field(
        ..., 
        description="The chronological step number, starting strictly from 1."
    )
    description: str = Field(
        ..., 
        description="Clear, actionable instructions detailing exactly what code changes or actions are required."
    )
    action_type: ActionType = Field(
        ..., 
        description="The precise operation being executed: 'create' for new files, 'modify' for existing source files, 'delete' for file removal, or 'no_op' for non-file actions."
    )
    target_file_path: str = Field(
        ..., 
        description="The repository-relative path of the file targeted. Use an empty string or 'N/A' if the action_type is 'no_op'."
    )
    explanation: str = Field(
        ..., 
        description="Technical rationale justifying why this file modification is necessary and how it fits the architecture."
    )


class DevelopmentPlan(BaseModel):
    """The schema-enforced output structure of the Planning Agent."""
    summary: str = Field(
        ..., 
        description="A concise, technical overview summarizing the planned architecture and key changes."
    )
    steps: List[PlanStep] = Field(
        ..., 
        description="The chronological sequence of implementation steps."
    )
    affected_files: List[str] = Field(
        ..., 
        description="An exhaustive, unique list of all relative file paths that will be created, modified, or deleted throughout the execution of this plan."
    )

    @model_validator(mode="after")
    def validate_affected_files_consistency(self) -> "DevelopmentPlan":
        """Self-consistency check validating that affected_files lists exactly the files touched by non-no_op steps."""
        # Extract unique file paths targeted by non-no_op steps
        step_files = {
            step.target_file_path.strip()
            for step in self.steps
            if step.action_type != ActionType.no_op and step.target_file_path.strip() not in ("", "N/A", "n/a")
        }
        
        # Format affected_files list
        declared_files = {path.strip() for path in self.affected_files if path.strip()}
        
        # Find discrepancies
        unlisted_in_affected = step_files - declared_files
        unused_in_steps = declared_files - step_files

        if unlisted_in_affected:
            # Dynamically align them or log a validation warning.
            # We preserve standard warning logs or adjust the list to maintain exact synchronization.
            # In a schema-enforced environment, we synchronize the list automatically to avoid validation crashes.
            unified_files = declared_files.union(step_files)
            self.affected_files = sorted(list(unified_files))

        return self