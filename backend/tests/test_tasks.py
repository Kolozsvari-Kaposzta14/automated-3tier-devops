
"""Automated API integration tests for task lifecycle management."""


def create_test_task(
    client,
    title="Test task",
    description="Task created during automated testing",
    status="todo",
):
    """Create a task through the API and return its response data."""

    # Use the public API rather than inserting directly into
    # the database. This exercises the actual application logic.
    response = client.post(
        "/api/tasks",
        json={
            "title": title,
            "description": description,
            "status": status,
        },
    )

    # Fail immediately if test data could not be created.
    assert response.status_code == 201, response.text

    # Return the generated task, including its database ID.
    return response.json()


def test_list_tasks_empty(client):
    """CRUD-001: A fresh database must contain no tasks."""

    # Retrieve all tasks from the isolated test database.
    response = client.get("/api/tasks")

    # Verify successful request processing.
    assert response.status_code == 200

    # The function-scoped fixture provides a fresh database,
    # so no tasks should exist before this test creates any.
    assert response.json() == []


def test_create_task_with_defaults(client):
    """CRUD-002: Creating a task applies the expected defaults."""

    # Supply only the required title field.
    # The backend must provide the remaining default values.
    response = client.post(
        "/api/tasks",
        json={"title": "Configure CI pipeline"},
    )

    # HTTP 201 indicates successful resource creation.
    assert response.status_code == 201

    task = response.json()

    # Verify that the database generated a valid task ID.
    assert isinstance(task["id"], int)
    assert task["id"] > 0

    # Verify the supplied title and default field values.
    assert task["title"] == "Configure CI pipeline"
    assert task["description"] == ""
    assert task["status"] == "todo"

    # Verify that a creation timestamp was generated.
    assert isinstance(task["created_at"], str)
    assert task["created_at"]


def test_create_task_with_explicit_values(client):
    """CRUD-003: Creating a task preserves supplied field values."""

    payload = {
        "title": "Build Docker images",
        "description": "Build frontend and backend containers",
        "status": "in_progress",
    }

    # Submit a task containing all writable fields.
    response = client.post("/api/tasks", json=payload)

    assert response.status_code == 201

    task = response.json()

    # Verify that the response preserves the supplied data.
    assert task["title"] == payload["title"]
    assert task["description"] == payload["description"]
    assert task["status"] == payload["status"]

    # Verify that server-generated fields are present.
    assert isinstance(task["id"], int)
    assert task["id"] > 0
    assert task["created_at"]


def test_get_task_by_id(client):
    """CRUD-004: Retrieve an existing task using its unique ID."""

    # Arrange: create a task using the shared helper function.
    created_task = create_test_task(
        client,
        title="Configure Nginx",
    )

    task_id = created_task["id"]

    # Act: retrieve the task using its generated identifier.
    response = client.get(f"/api/tasks/{task_id}")

    # Assert: verify the HTTP response and persisted data.
    assert response.status_code == 200
    assert response.json() == created_task


def test_list_tasks_in_descending_id_order(client):
    """CRUD-005: Tasks must be returned in descending ID order."""

    # Create three independent tasks in a known sequence.
    first_task = create_test_task(
        client,
        title="Configure infrastructure",
    )

    second_task = create_test_task(
        client,
        title="Build application",
    )

    third_task = create_test_task(
        client,
        title="Deploy application",
    )

    # Retrieve all tasks from the database.
    response = client.get("/api/tasks")

    assert response.status_code == 200

    tasks = response.json()

    # Verify that all three tasks were persisted.
    assert len(tasks) == 3

    # The API contract specifies descending database ID order.
    # The most recently inserted task should appear first.
    expected_ids = [
        third_task["id"],
        second_task["id"],
        first_task["id"],
    ]

    actual_ids = [task["id"] for task in tasks]

    assert actual_ids == expected_ids

    # Verify that the returned records contain the expected data.
    assert tasks == [third_task, second_task, first_task]



def test_update_task_title(client):
    """CRUD-006: Updating a task title persists the new value."""

    # Arrange: create a task with an initial title.
    task = create_test_task(
        client,
        title="Initial task title",
    )

    task_id = task["id"]
    new_title = "Updated task title"

    # Act: update only the title using PATCH.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"title": new_title},
    )

    # Assert: verify that the update was successful.
    assert response.status_code == 200

    updated_task = response.json()

    # Verify the updated title and unchanged task identity.
    assert updated_task["title"] == new_title
    assert updated_task["id"] == task_id

    # Retrieve the task again to verify database persistence.
    persisted_response = client.get(f"/api/tasks/{task_id}")

    assert persisted_response.status_code == 200
    assert persisted_response.json() == updated_task


def test_update_task_description(client):
    """CRUD-007: Updating a description persists the new value."""

    # Arrange: create a task with an initial description.
    task = create_test_task(
        client,
        description="Initial description",
    )

    task_id = task["id"]
    new_description = "Updated deployment instructions"

    # Act: modify only the task description.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"description": new_description},
    )

    # Assert: verify the successful update.
    assert response.status_code == 200

    updated_task = response.json()

    assert updated_task["description"] == new_description
    assert updated_task["id"] == task_id

    # Confirm that the change was committed to the database.
    persisted_response = client.get(f"/api/tasks/{task_id}")

    assert persisted_response.status_code == 200
    assert persisted_response.json() == updated_task


def test_move_task_to_in_progress(client):
    """CRUD-008: Move a task from To do to In progress."""

    # Arrange: create a task in the initial Kanban column.
    task = create_test_task(
        client,
        title="Implement GitHub Actions",
        status="todo",
    )

    task_id = task["id"]

    assert task["status"] == "todo"

    # Act: simulate the frontend moving the task
    # into the In progress column.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"status": "in_progress"},
    )

    # Assert: verify the new workflow status.
    assert response.status_code == 200

    updated_task = response.json()

    assert updated_task["status"] == "in_progress"
    assert updated_task["id"] == task_id

    # Verify that the new status survives a separate request.
    persisted_response = client.get(f"/api/tasks/{task_id}")

    assert persisted_response.status_code == 200
    assert persisted_response.json() == updated_task


def test_move_task_to_done(client):
    """CRUD-009: Move a task from In progress to Done."""

    # Arrange: create a task that is already in progress.
    task = create_test_task(
        client,
        title="Complete backend testing",
        status="in_progress",
    )

    task_id = task["id"]

    assert task["status"] == "in_progress"

    # Act: simulate completion of the task.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"status": "done"},
    )

    # Assert: verify that the task is marked as completed.
    assert response.status_code == 200

    updated_task = response.json()

    assert updated_task["status"] == "done"
    assert updated_task["id"] == task_id

    # Confirm that the completed status was persisted.
    persisted_response = client.get(f"/api/tasks/{task_id}")

    assert persisted_response.status_code == 200
    assert persisted_response.json() == updated_task


def test_partial_update_preserves_other_fields(client):
    """CRUD-010: PATCH must preserve fields omitted by the caller."""

    # Arrange: create a task containing all writable fields.
    original_task = create_test_task(
        client,
        title="Deploy staging environment",
        description="Deploy containers using Docker Compose",
        status="todo",
    )

    task_id = original_task["id"]

    # Act: update only the task status.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"status": "in_progress"},
    )

    assert response.status_code == 200

    updated_task = response.json()

    # Construct the expected response by copying the
    # original task and changing only its status.
    expected_task = {
        **original_task,
        "status": "in_progress",
    }

    # Assert: every field except status must remain unchanged.
    # This includes the title, description, ID and timestamp.
    assert updated_task == expected_task

    # Verify the complete persisted record.
    persisted_response = client.get(f"/api/tasks/{task_id}")

    assert persisted_response.status_code == 200
    assert persisted_response.json() == expected_task



def test_delete_existing_task(client):
    """CRUD-011: Deleting a task removes it from the database."""

    # Arrange: create a task that will be deleted.
    task = create_test_task(
        client,
        title="Temporary deployment task",
    )

    task_id = task["id"]

    # Confirm that the task exists before attempting deletion.
    initial_response = client.get(f"/api/tasks/{task_id}")

    assert initial_response.status_code == 200
    assert initial_response.json() == task

    # Act: send an HTTP DELETE request for the task.
    response = client.delete(f"/api/tasks/{task_id}")

    # Assert: HTTP 204 confirms successful deletion.
    assert response.status_code == 204

    # HTTP 204 responses must not contain a response body.
    assert response.content == b""

    # Attempt to retrieve the deleted task.
    # The backend must return HTTP 404 because the
    # database record should no longer exist.
    deleted_response = client.get(f"/api/tasks/{task_id}")

    assert deleted_response.status_code == 404
    assert deleted_response.json() == {
        "detail": "Task not found",
    }

    # Verify that the deleted task is also absent
    # from the complete task collection.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_task_preserves_other_tasks(client):
    """CRUD-012: Deleting one task must not affect other tasks."""

    # Arrange: create three independent tasks representing
    # the three Kanban workflow stages.
    first_task = create_test_task(
        client,
        title="Configure infrastructure",
        status="todo",
    )

    second_task = create_test_task(
        client,
        title="Temporary task to remove",
        status="in_progress",
    )

    third_task = create_test_task(
        client,
        title="Complete application build",
        status="done",
    )

    # Act: delete only the second task.
    response = client.delete(
        f"/api/tasks/{second_task['id']}"
    )

    assert response.status_code == 204
    assert response.content == b""

    # Verify that the deleted task is no longer accessible.
    deleted_response = client.get(
        f"/api/tasks/{second_task['id']}"
    )

    assert deleted_response.status_code == 404
    assert deleted_response.json() == {
        "detail": "Task not found",
    }

    # Retrieve the remaining task collection.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200

    remaining_tasks = list_response.json()

    # Exactly two tasks should remain in the database.
    assert len(remaining_tasks) == 2

    # Verify that only the requested task was deleted.
    # The API must preserve descending ID order and
    # all original fields of the remaining tasks.
    assert remaining_tasks == [third_task, first_task]

    # Independently retrieve the first surviving task.
    first_response = client.get(
        f"/api/tasks/{first_task['id']}"
    )

    assert first_response.status_code == 200
    assert first_response.json() == first_task

    # Independently retrieve the third surviving task.
    third_response = client.get(
        f"/api/tasks/{third_task['id']}"
    )

    assert third_response.status_code == 200
    assert third_response.json() == third_task



def test_get_nonexistent_task(client):
    """CRUD-013: Retrieving a nonexistent task returns HTTP 404."""

    # The isolated database is initially empty.
    # Therefore, this task ID cannot reference an existing record.
    nonexistent_id = 999999

    # Attempt to retrieve the nonexistent task.
    response = client.get(f"/api/tasks/{nonexistent_id}")

    # Verify the expected HTTP error and response contract.
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_update_nonexistent_task(client):
    """CRUD-014: Updating a nonexistent task returns HTTP 404."""

    nonexistent_id = 999999

    # Submit a valid update payload for a nonexistent resource.
    # Using valid data ensures that resource existence,
    # rather than request validation, is being tested.
    response = client.patch(
        f"/api/tasks/{nonexistent_id}",
        json={"status": "done"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}

    # Verify that PATCH did not accidentally create a task.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_nonexistent_task(client):
    """CRUD-015: Deleting a nonexistent task returns HTTP 404."""

    # Create a valid task to verify that the failed deletion
    # does not affect an existing database record.
    existing_task = create_test_task(
        client,
        title="Task that must remain unchanged",
    )

    nonexistent_id = existing_task["id"] + 1000

    # Attempt to delete a different, nonexistent task.
    response = client.delete(
        f"/api/tasks/{nonexistent_id}"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}

    # Confirm that the existing task remains unchanged.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json() == [existing_task]


def test_create_task_without_title(client):
    """CRUD-016: Creating a task without a title is rejected."""

    # Deliberately omit the required title field.
    response = client.post(
        "/api/tasks",
        json={"description": "Missing required title"},
    )

    # FastAPI must reject the invalid request payload.
    assert response.status_code == 422

    errors = response.json()["detail"]

    # Verify that validation failed specifically because
    # the required title field was missing.
    assert any(
        error["loc"] == ["body", "title"]
        and error["type"] == "missing"
        for error in errors
    )

    # Confirm that the invalid request created no record.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json() == []


def test_create_task_with_empty_title(client):
    """CRUD-017: Creating a task with an empty title is rejected."""

    # Submit a title that violates the minimum length.
    response = client.post(
        "/api/tasks",
        json={"title": ""},
    )

    assert response.status_code == 422

    errors = response.json()["detail"]

    # Verify that the minimum string length rule was enforced.
    assert any(
        error["loc"] == ["body", "title"]
        and error["type"] == "string_too_short"
        for error in errors
    )

    # Verify that no invalid task was persisted.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json() == []


def test_create_task_with_oversized_title(client):
    """CRUD-018: Titles longer than 120 characters are rejected."""

    # Generate a title containing 121 characters.
    # This exceeds the maximum permitted length by one.
    oversized_title = "A" * 121

    response = client.post(
        "/api/tasks",
        json={"title": oversized_title},
    )

    assert response.status_code == 422

    errors = response.json()["detail"]

    # Verify that the maximum string length rule was enforced.
    assert any(
        error["loc"] == ["body", "title"]
        and error["type"] == "string_too_long"
        for error in errors
    )

    # Confirm that the invalid task was not stored.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json() == []


def test_create_task_with_invalid_status(client):
    """CRUD-019: Creating a task with an invalid status is rejected."""

    # "completed" is not one of the three permitted
    # Kanban workflow status values.
    response = client.post(
        "/api/tasks",
        json={
            "title": "Invalid workflow status",
            "status": "completed",
        },
    )

    assert response.status_code == 422

    errors = response.json()["detail"]

    # Verify that validation failed on the status enum.
    assert any(
        error["loc"] == ["body", "status"]
        and error["type"] == "enum"
        for error in errors
    )

    # Confirm that no invalid task was persisted.
    list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json() == []


def test_update_task_with_invalid_status(client):
    """CRUD-020: An invalid status update must preserve the task."""

    # Arrange: create a valid task in the To do column.
    original_task = create_test_task(
        client,
        title="Task with valid workflow status",
        status="todo",
    )

    task_id = original_task["id"]

    # Act: attempt to assign an unsupported status.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"status": "archived"},
    )

    # Assert: the invalid update must be rejected.
    assert response.status_code == 422

    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "status"]
        and error["type"] == "enum"
        for error in errors
    )

    # Retrieve the original task through a separate request.
    persisted_response = client.get(
        f"/api/tasks/{task_id}"
    )

    assert persisted_response.status_code == 200

    # Verify that the failed update did not modify any field,
    # including the original status and creation timestamp.
    assert persisted_response.json() == original_task

def test_update_task_with_null_title(client):
    """CRUD-021: An explicitly null title must be rejected."""

    # Arrange:
    # Create a valid task with a non-null title.
    original_task = create_test_task(
        client,
        title="Original task title",
    )

    task_id = original_task["id"]

    # Act:
    # Python None is serialized by HTTPX into JSON null.
    # This explicitly attempts to remove the required title.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"title": None},
    )

    # Assert:
    # The API must reject the request before modifying
    # the database record.
    assert response.status_code == 422

    # Verify that the validation error identifies
    # the correct request body field.
    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "title"]
        for error in errors
    )

    # Retrieve the task again to confirm that the
    # rejected request did not modify persisted data.
    persisted_response = client.get(
        f"/api/tasks/{task_id}"
    )

    assert persisted_response.status_code == 200
    assert persisted_response.json() == original_task


def test_update_task_with_null_description(client):
    """CRUD-022: An explicitly null description must be rejected."""

    # Arrange:
    # Create a task containing a valid description.
    original_task = create_test_task(
        client,
        title="Task with a valid description",
        description="Original deployment instructions",
    )

    task_id = original_task["id"]

    # Act:
    # Attempt to assign null to the non-nullable
    # description field.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"description": None},
    )

    # Assert:
    # Request validation must reject the null value.
    assert response.status_code == 422

    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "description"]
        for error in errors
    )

    # Confirm that the original task remains unchanged.
    persisted_response = client.get(
        f"/api/tasks/{task_id}"
    )

    assert persisted_response.status_code == 200
    assert persisted_response.json() == original_task


def test_update_task_with_null_status(client):
    """CRUD-023: An explicitly null status must be rejected."""

    # Arrange:
    # Create a task in a valid Kanban workflow stage.
    original_task = create_test_task(
        client,
        title="Task with a valid workflow status",
        status="in_progress",
    )

    task_id = original_task["id"]

    # Act:
    # Attempt to remove the required workflow status.
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"status": None},
    )

    # Assert:
    # The API must reject the invalid workflow status.
    assert response.status_code == 422

    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "status"]
        for error in errors
    )

    # Confirm that the task remains in its original
    # Kanban stage and that no fields were modified.
    persisted_response = client.get(
        f"/api/tasks/{task_id}"
    )

    assert persisted_response.status_code == 200
    assert persisted_response.json() == original_task
