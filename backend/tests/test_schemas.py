"""Unit tests for Pydantic task request and response models."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas import (
    TaskCreate,
    TaskRead,
    TaskStatus,
    TaskUpdate,
)


# ============================================================
# TaskStatus enum tests
# ============================================================


@pytest.mark.parametrize(
    "status, expected",
    [
        ("todo", TaskStatus.TODO),
        ("in_progress", TaskStatus.IN_PROGRESS),
        ("done", TaskStatus.DONE),
    ],
)
def test_task_status_values(status, expected):
    """Verify that every supported Kanban status is recognized."""

    assert TaskStatus(status) is expected


# ============================================================
# TaskCreate unit tests
# ============================================================


def test_task_create_defaults():
    """Verify default values when optional fields are omitted."""

    task = TaskCreate(title="Deploy application")

    assert task.title == "Deploy application"
    assert task.description == ""
    assert task.status is TaskStatus.TODO


def test_task_create_explicit_values():
    """Verify that explicitly supplied values are preserved."""

    task = TaskCreate(
        title="Deploy application",
        description="Deploy the staging environment",
        status="in_progress",
    )

    assert task.title == "Deploy application"
    assert task.description == "Deploy the staging environment"
    assert task.status is TaskStatus.IN_PROGRESS


@pytest.mark.parametrize("length", [1, 120])
def test_task_create_valid_title_boundaries(length):
    """Accept the minimum and maximum supported title lengths."""

    title = "A" * length

    task = TaskCreate(title=title)

    assert task.title == title


@pytest.mark.parametrize("length", [0, 1000])
def test_task_create_valid_description_boundaries(length):
    """Accept empty and maximum-length descriptions."""

    description = "A" * length

    task = TaskCreate(
        title="Test description boundaries",
        description=description,
    )

    assert task.description == description


@pytest.mark.parametrize(
    "payload, field, error_type",
    [
        ({}, "title", "missing"),
        ({"title": ""}, "title", "string_too_short"),
        (
            {"title": "A" * 121},
            "title",
            "string_too_long",
        ),
        (
            {"title": "Valid", "description": "A" * 1001},
            "description",
            "string_too_long",
        ),
        (
            {"title": "Valid", "status": "archived"},
            "status",
            "enum",
        ),
        ({"title": None}, "title", "string_type"),
        (
            {"title": "Valid", "description": None},
            "description",
            "string_type",
        ),
        (
            {"title": "Valid", "status": None},
            "status",
            "enum",
        ),
        ({"title": 123}, "title", "string_type"),
    ],
)
def test_task_create_rejects_invalid_input(
    payload,
    field,
    error_type,
):
    """Reject invalid creation payloads with field-level errors."""

    # pytest.raises verifies that model construction fails.
    with pytest.raises(ValidationError) as exc_info:
        TaskCreate(**payload)

    # Inspect structured validation errors rather than
    # relying on human-readable exception messages.
    errors = exc_info.value.errors()

    assert any(
        error["loc"] == (field,)
        and error["type"] == error_type
        for error in errors
    )


# ============================================================
# TaskUpdate unit tests
# ============================================================


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "Updated title"},
        {"description": "Updated description"},
        {"description": ""},
        {"status": "todo"},
        {"status": "in_progress"},
        {"status": "done"},
        {
            "title": "Updated title",
            "description": "Updated description",
            "status": "done",
        },
    ],
)
def test_task_update_valid_partial_payloads(payload):
    """Verify that only explicitly supplied fields are serialized."""

    task = TaskUpdate(**payload)

    # exclude_unset prevents omitted fields from appearing
    # in the payload passed to our database update logic.
    assert task.model_dump(
        mode="json",
        exclude_unset=True,
    ) == payload

    # Confirm that Pydantic tracks exactly the fields
    # explicitly provided by the caller.
    assert task.model_fields_set == set(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "A"},
        {"title": "A" * 120},
        {"description": "A" * 1000},
    ],
)
def test_task_update_valid_boundaries(payload):
    """Accept valid boundary lengths during partial updates."""

    task = TaskUpdate(**payload)

    assert task.model_dump(
        mode="json",
        exclude_unset=True,
    ) == payload


@pytest.mark.parametrize(
    "payload, field, error_type",
    [
        ({"title": ""}, "title", "string_too_short"),
        (
            {"title": "A" * 121},
            "title",
            "string_too_long",
        ),
        (
            {"description": "A" * 1001},
            "description",
            "string_too_long",
        ),
        ({"status": "archived"}, "status", "enum"),
        ({"title": 123}, "title", "string_type"),
    ],
)
def test_task_update_rejects_invalid_input(
    payload,
    field,
    error_type,
):
    """Preserve native Pydantic validation error behavior."""

    with pytest.raises(ValidationError) as exc_info:
        TaskUpdate(**payload)

    errors = exc_info.value.errors()

    # REG-001 and REG-002:
    # Invalid fields must retain their original error
    # locations and native validation error types.
    assert any(
        error["loc"] == (field,)
        and error["type"] == error_type
        for error in errors
    )


@pytest.mark.parametrize(
    "field",
    ["title", "description", "status"],
)
def test_task_update_rejects_explicit_null(field):
    """Prevent explicit null values from reaching persistence."""

    # BUG-001 regression protection at the unit-test level.
    with pytest.raises(ValidationError) as exc_info:
        TaskUpdate(**{field: None})

    errors = exc_info.value.errors()

    assert len(errors) == 1
    assert errors[0]["loc"] == (field,)
    assert errors[0]["type"] == "value_error"
    assert "Field must not be null" in errors[0]["msg"]


# ============================================================
# TaskRead unit tests
# ============================================================


def test_task_read_from_attributes():
    """Verify conversion from an attribute-based object."""

    created_at = datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )

    # Simulate an ORM object's attributes without creating
    # a database connection or SQLAlchemy session.
    source = SimpleNamespace(
        id=1,
        title="Deploy application",
        description="Staging deployment",
        status="done",
        created_at=created_at,
    )

    task = TaskRead.model_validate(source)

    assert task.id == 1
    assert task.title == "Deploy application"
    assert task.description == "Staging deployment"
    assert task.status is TaskStatus.DONE
    assert task.created_at == created_at


def test_task_read_json_serialization():
    """Verify that response data can be serialized to JSON."""

    created_at = datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )

    task = TaskRead(
        id=1,
        title="Deploy application",
        description="",
        status="done",
        created_at=created_at,
    )

    result = task.model_dump(mode="json")

    assert result["id"] == 1
    assert result["title"] == "Deploy application"
    assert result["description"] == ""
    assert result["status"] == "done"

    # Verify that the serialized timestamp preserves
    # the original datetime value and timezone.
    assert datetime.fromisoformat(
        result["created_at"]
    ) == created_at


# ============================================================
# Pydantic JSON Schema contract test
# ============================================================


def test_task_update_json_schema_contract():
    """Document PATCH fields as optional but non-nullable."""

    schema = TaskUpdate.model_json_schema(
        mode="validation"
    )

    properties = schema["properties"]

    # All supported PATCH properties must be documented.
    assert set(properties) == {
        "title",
        "description",
        "status",
    }

    # PATCH requests must permit omitted fields.
    assert not schema.get("required", [])

    # API-001:
    # Verify that generated property definitions contain
    # only the intended non-nullable input types.
    assert properties["title"]["type"] == "string"
    assert properties["title"]["minLength"] == 1
    assert properties["title"]["maxLength"] == 120

    assert properties["description"]["type"] == "string"
    assert properties["description"]["maxLength"] == 1000

    assert (
        properties["status"]["$ref"]
        == "#/$defs/TaskStatus"
    )

    # Ensure the nullable alternatives and misleading
    # defaults have been removed from every PATCH field.
    for definition in properties.values():
        assert "anyOf" not in definition
        assert "default" not in definition

    # Preserve the supported Kanban workflow stages.
    assert schema["$defs"]["TaskStatus"]["enum"] == [
        "todo",
        "in_progress",
        "done",
    ]
