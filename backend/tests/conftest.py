
"""Shared fixtures for isolated backend API testing."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# Force the test process to use SQLite before importing
# application modules that initialize database settings.
#
# This environment variable affects only the Pytest process
# and its child processes, not the parent WSL shell or
# the running Docker containers.
os.environ["DATABASE_URL"] = "sqlite://"


@pytest.fixture
def client(monkeypatch):
    """Provide an isolated FastAPI client for each test."""

    # Import application modules after the test database
    # environment variable has been configured.
    from app import main
    from app.database import get_db

    # Create a temporary SQLite database in memory.
    #
    # StaticPool ensures that all database sessions share
    # the same underlying in-memory database connection.
    #
    # check_same_thread=False allows FastAPI's worker
    # threads to access the SQLite connection.
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create a session factory bound exclusively to the
    # temporary testing database.
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_get_db():
        """Provide a temporary database session per request."""

        # The context manager automatically closes the
        # database session after the request finishes.
        with TestingSessionLocal() as session:
            yield session

    # Replace the engine referenced by FastAPI's lifespan.
    #
    # This ensures that startup table creation happens
    # inside the temporary database, not PostgreSQL.
    #
    # Pytest automatically restores this attribute after
    # the test completes.
    monkeypatch.setattr(main, "engine", test_engine)

    # Preserve existing dependency overrides so they can
    # be restored after the test.
    original_overrides = main.app.dependency_overrides.copy()

    # Redirect all API database requests to the test engine.
    main.app.dependency_overrides[get_db] = override_get_db

    try:
        # Using TestClient as a context manager executes
        # FastAPI's startup and shutdown lifespan events.
        #
        # The existing lifespan creates the required tables
        # inside our isolated SQLite database.
        with TestClient(main.app) as test_client:
            yield test_client

    finally:
        # Restore the application's original dependency
        # configuration, even if the test fails.
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(original_overrides)

        # Release the database connection and destroy
        # the temporary in-memory database.
        test_engine.dispose()
