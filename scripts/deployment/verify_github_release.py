"""Verify release workflow metadata using GitHub's REST API.

This program performs read-only verification.
It does not download executable code, authenticate to AWS,
pull Docker images, or start containers.

Successful verification is one prerequisite for deployment.
It does not independently authenticate the manifest's digests.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from validate_release import validate_manifest


# Explicitly restrict verification to our project.
REPOSITORY = (
    "Kolozsvari-Kaposzta14/automated-3tier-devops"
)

REPOSITORY_ID = 1461631005
OWNER_ID = 243810014

API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"

EXPECTED_WORKFLOW_PATH = ".github/workflows/cd.yml"
EXPECTED_WORKFLOW_NAME = "Continuous Deployment"

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def require(condition, message):
    """Reject metadata that does not meet our requirements."""
    if not condition:
        raise ValueError(message)


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent API requests from following redirects."""

    def redirect_request(
        self, req, fp, code, msg, headers, newurl
    ):
        raise ValueError("Unexpected GitHub API redirect")


def github_get(endpoint):
    """Retrieve bounded JSON data from the approved API."""

    request = urllib.request.Request(
        API_ROOT + endpoint,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "automated-3tier-release-verifier",
        },
    )

    # No personal access token is required for these
    # public repository metadata requests.
    opener = urllib.request.build_opener(
        RejectRedirects()
    )

    with opener.open(request, timeout=30) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)

    require(
        len(raw) <= MAX_RESPONSE_BYTES,
        "GitHub API response exceeds size limit",
    )

    result = json.loads(raw)

    require(
        isinstance(result, dict),
        "Unexpected GitHub API response",
    )

    return result


def verify_run(manifest, run, workflow):
    """Compare GitHub metadata against the validated manifest."""

    repository = run.get("repository") or {}
    head_repository = run.get("head_repository") or {}
    owner = repository.get("owner") or {}

    checks = [
        (
            repository.get("id") == REPOSITORY_ID,
            "Expected GitHub repository ID",
        ),
        (
            owner.get("id") == OWNER_ID,
            "Expected repository owner ID",
        ),
        (
            repository.get("full_name") == REPOSITORY,
            "Expected repository name",
        ),
        (
            head_repository.get("id") == REPOSITORY_ID,
            "Workflow source is our repository",
        ),
        (
            str(run.get("id")) == manifest["run_id"],
            "Workflow run ID matches manifest",
        ),
        (
            str(run.get("run_attempt"))
            == manifest["run_attempt"],
            "Workflow run attempt matches manifest",
        ),
        (
            run.get("head_sha") == manifest["commit_sha"],
            "Workflow commit matches manifest",
        ),
        (
            run.get("head_branch") == "main",
            "Workflow executed against main",
        ),
        (
            run.get("event") in {
                "push",
                "workflow_dispatch",
            },
            "Approved workflow trigger",
        ),
        (
            workflow.get("path") == EXPECTED_WORKFLOW_PATH,
            "Expected CD workflow path",
        ),
        (
            workflow.get("name") == EXPECTED_WORKFLOW_NAME,
            "Expected CD workflow name",
        ),
        (
            run.get("workflow_id") == workflow.get("id"),
            "Expected CD workflow identity",
        ),
        (
            run.get("status") == "completed",
            "Workflow execution completed",
        ),
        (
            run.get("conclusion") == "success",
            "Workflow execution successful",
        ),
    ]

    for condition, message in checks:
        require(condition, message)
        print(f"PASS: {message}")

    print(f"Workflow assertions passed: {len(checks)}")


def verify_artifact_metadata(manifest, artifacts):
    """Confirm that the expected release artifact exists."""

    expected_name = (
        "release-manifest-" + manifest["release_tag"]
    )

    candidates = [
        artifact
        for artifact in artifacts.get("artifacts", [])
        if artifact.get("name") == expected_name
    ]

    require(
        len(candidates) == 1,
        "Expected unique release manifest artifact",
    )

    artifact = candidates[0]

    require(
        artifact.get("expired") is False,
        "Release manifest artifact has expired",
    )

    require(
        type(artifact.get("size_in_bytes")) is int
        and artifact["size_in_bytes"] > 0,
        "Invalid release artifact size",
    )

    print("PASS: Expected release artifact exists")
    print("PASS: Release artifact has not expired")
    print("PASS: Release artifact is nonempty")


def main():
    parser = argparse.ArgumentParser(
        description="Verify GitHub release workflow metadata."
    )

    parser.add_argument("manifest", type=Path)

    args = parser.parse_args()

    try:
        # Validate all external input before using its
        # workflow identifiers in API requests.
        manifest = validate_manifest(args.manifest)

        run_id = manifest["run_id"]
        attempt = manifest["run_attempt"]

        # Retrieve the exact workflow execution attempt,
        # rather than assuming the latest attempt is correct.
        run = github_get(
            f"/actions/runs/{run_id}/attempts/{attempt}"
        )

        workflow = github_get(
            "/actions/workflows/cd.yml"
        )

        verify_run(manifest, run, workflow)

        artifacts = github_get(
            f"/actions/runs/{run_id}/artifacts?per_page=100"
        )

        # Fail closed if additional artifact pages exist.
        require(
            artifacts.get("total_count", 0)
            <= len(artifacts.get("artifacts", [])),
            "Artifact listing requires pagination",
        )

        verify_artifact_metadata(manifest, artifacts)

    except urllib.error.HTTPError as error:
        print(
            f"FAIL: GitHub API returned HTTP {error.code}",
            file=sys.stderr,
        )
        return 1

    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
    ):
        print(
            "FAIL: GitHub release verification rejected.",
            file=sys.stderr,
        )
        return 1

    print()
    print("GitHub release metadata verification: PASS")
    print(f"Release: {manifest['release_tag']}")
    print(f"Commit: {manifest['commit_sha']}")
    print(f"Workflow run: {manifest['run_id']}")
    print(f"Run attempt: {manifest['run_attempt']}")

    print(
        "NOTE: ECR digest verification and deployment "
        "authorization are still required."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
