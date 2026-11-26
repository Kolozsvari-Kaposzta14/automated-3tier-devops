
"""Automated tests for the backend health endpoint."""


def test_health_endpoint(client):
    """Verify that the API and its database connection are healthy."""

    # Send an HTTP GET request to the health endpoint.
    # The client fixture is automatically provided by conftest.py.
    #
    # The request executes against the FastAPI application
    # using our isolated in-memory SQLite database.
    response = client.get("/api/health")

    # Verify that the endpoint returns HTTP 200 OK.
    # Any unexpected status code causes the test to fail.
    assert response.status_code == 200

    # Verify that the response uses the JSON content type.
    # This confirms that the endpoint returns structured API data.
    assert response.headers["content-type"].startswith(
        "application/json"
    )

    # Verify the exact response body.
    # The health endpoint must confirm successful operation.
    assert response.json() == {"status": "ok"}
