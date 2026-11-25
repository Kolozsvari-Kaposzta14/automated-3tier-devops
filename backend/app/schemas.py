
"""Separate public request/response contracts from database internals."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(str, Enum):
    """Define the supported Kanban workflow stages."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskCreate(BaseModel):
    """Validate the request body when creating a new task."""

    # A task must have a non-empty title containing
    # no more than 120 characters.
    title: str = Field(min_length=1, max_length=120)

    # An omitted description defaults to an empty string.
    description: str = Field(default="", max_length=1000)

    # Newly created tasks enter the To do column by default.
    status: TaskStatus = TaskStatus.TODO


class TaskUpdate(BaseModel):
    """Validate partial updates to existing tasks."""

    @staticmethod
    def customize_json_schema(schema: dict) -> None:
        """Document PATCH fields as optional but non-nullable."""

        # API-001:
        # Modify only the generated JSON Schema.
        # Do not modify Pydantic's runtime validation annotations.
        properties = schema.get("properties", {})

        # Restrict customization to the known PATCH fields.
        for field_name in ("title", "description", "status"):
            property_schema = properties.get(field_name, {})

            # Nullable annotations normally generate an anyOf
            # containing the accepted type and a null alternative.
            alternatives = property_schema.get("anyOf", [])

            # Retain every alternative except the explicit null type.
            non_null_alternatives = [
                alternative
                for alternative in alternatives
                if alternative.get("type") != "null"
            ]

            # Only rewrite unions from which null was removed.
            if (
                non_null_alternatives
                and len(non_null_alternatives) < len(alternatives)
            ):
                if len(non_null_alternatives) == 1:
                    # A single remaining alternative does not
                    # require an anyOf wrapper.
                    property_schema.pop("anyOf")
                    property_schema.update(
                        non_null_alternatives[0]
                    )
                else:
                    # Preserve unions containing multiple
                    # legitimate non-null alternatives.
                    property_schema["anyOf"] = non_null_alternatives

            # Remove the documented null default.
            # The actual internal Python default remains unchanged.
            if property_schema.get("default") is None:
                property_schema.pop("default", None)

    # Register the documentation-only customization.
    model_config = ConfigDict(
        json_schema_extra=customize_json_schema,
    )

    # REG-001:
    # Restore the original runtime annotations to preserve
    # Pydantic's native validation behavior and error structure.
    #
    # None remains the internal default for omitted fields.
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    status: TaskStatus | None = None

    # BUG-001:
    # Reject explicitly supplied null values before they reach
    # the FastAPI endpoint or database persistence layer.
    @field_validator(
        "title",
        "description",
        "status",
        mode="before",
    )
    @classmethod
    def reject_explicit_null(cls, value):
        """Reject explicit null values in partial task updates."""

        # Omitted fields retain their internal defaults.
        # Explicitly supplied null values are rejected.
        if value is None:
            raise ValueError("Field must not be null")

        # Continue normal Pydantic validation.
        return value


class TaskRead(BaseModel):
    """Define the public representation of a persisted task."""

    # Allow Pydantic to read attributes directly from
    # SQLAlchemy ORM model instances.
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: TaskStatus
    created_at: datetime
