"""Verify explicit GitHub authorization for production deployment.

This module is intentionally read-only.

It verifies local staging acceptance, trusted workflow source,
GitHub execution metadata and explicit human approval.

Authorization consumption must be performed separately by the
deployment controller while holding its deployment lock.
"""

import argparse
import base64
import hashlib
import json
import re
import sys
import time

from datetime import datetime
from pathlib import Path
from urllib.request import (
    Request,
    ProxyHandler,
    HTTPRedirectHandler,
    build_opener,
)

from validate_release import validate_manifest


# ---------------------------------------------------------
# Trusted identities and security policy
# ---------------------------------------------------------

ROOT = Path.home() / ".local/share/automated-3tier-deploy"

REPOSITORY = (
    "Kolozsvari-Kaposzta14/"
    "automated-3tier-devops"
)

REPOSITORY_ID = 1461631005

OWNER_ID = 243810014

REVIEWER_ID = 243810014

PRODUCTION_ENVIRONMENT_ID = 28629232069

WORKFLOW_PATH = ".github/workflows/production-approval.yml"

WORKFLOW_NAME = "Production Approval"

WORKFLOW_SHA256 = (
    "e96b38a7d10de9d1bde7380b8241a98"
    "e0b2c230d46436947fd33b56ae1abe205"
)

API_BASE = f"https://api.github.com/repos/{REPOSITORY}"

MAX_RESPONSE_BYTES = 2 * 1024 * 1024

MAX_AUTHORIZATION_AGE = 24 * 60 * 60

EXPECTED_JOBS = {
    "Validate Production Request",
    "Authorize Production Release",
}


# ---------------------------------------------------------
# Common validation utilities
# ---------------------------------------------------------

class VerificationError(ValueError):
    """Raised when an authorization condition is not met."""


def require(condition, message):
    """Reject authorization immediately on validation failure."""

    if not condition:
        raise VerificationError(message)


def sha256_bytes(data):
    """Return a lowercase SHA-256 checksum."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    """Calculate the checksum of a local file."""

    return sha256_bytes(path.read_bytes())


def read_json(path):
    """Read a bounded local JSON document."""

    with path.open("rb") as file:
        raw = file.read(MAX_RESPONSE_BYTES + 1)

    require(
        len(raw) <= MAX_RESPONSE_BYTES,
        "Local JSON document exceeds size limit",
    )

    return json.loads(raw)


def timestamp(value):
    """Convert an ISO-8601 timestamp to Unix time."""

    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    require(
        parsed.tzinfo is not None,
        "Timestamp must include timezone information",
    )

    return parsed.timestamp()


def valid_sha256(value):
    """Validate a lowercase SHA-256 checksum."""

    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value)
        is not None
    )


def valid_run_id(value):
    """Validate a GitHub workflow run identifier."""

    return (
        isinstance(value, str)
        and re.fullmatch(r"[1-9][0-9]{0,19}", value)
        is not None
    )


# ---------------------------------------------------------
# Restricted GitHub API client
# ---------------------------------------------------------

class RejectRedirects(HTTPRedirectHandler):
    """Prevent requests from following unexpected redirects."""

    def redirect_request(self, *args, **kwargs):
        return None


OPENER = build_opener(
    ProxyHandler({}),
    RejectRedirects(),
)


def github_json(endpoint):
    """Retrieve bounded JSON from the trusted GitHub API."""

    require(
        endpoint.startswith("/")
        and not endpoint.startswith("//"),
        "Invalid GitHub API endpoint",
    )

    request = Request(
        API_BASE + endpoint,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "three-tier-production-verifier",
        },
        method="GET",
    )

    # No authentication token is required for this public repo.
    # Network failures propagate and prevent authorization.
    with OPENER.open(request, timeout=30) as response:

        require(
            response.status == 200,
            "Unexpected GitHub API response",
        )

        raw = response.read(MAX_RESPONSE_BYTES + 1)

    require(
        len(raw) <= MAX_RESPONSE_BYTES,
        "GitHub API response exceeds size limit",
    )

    return json.loads(raw)


# ---------------------------------------------------------
# Local staging acceptance verification
# ---------------------------------------------------------

def verify_local_acceptance(manifest_path, root=ROOT):
    """Bind production authorization to accepted staging data."""

    manifest_path = Path(manifest_path)

    manifest = validate_manifest(manifest_path)

    release_tag = manifest["release_tag"]

    acceptance_path = (
        root
        / "state"
        / f"staging-acceptance-{release_tag}.json"
    )

    state_path = root / "state/staging.json"

    acceptance = read_json(acceptance_path)

    state = read_json(state_path)

    manifest_hash = sha256_file(manifest_path)

    acceptance_hash = sha256_file(acceptance_path)

    require(
        state["environment"] == "staging",
        "Invalid staging deployment environment",
    )

    require(
        state["release"] == manifest,
        "Current staging release differs from requested release",
    )

    require(
        state["readiness"] == "passed"
        and state["integration_tests"] == "passed",
        "Staging deployment has not passed acceptance",
    )

    require(
        acceptance["schema_version"] == 1
        and acceptance["environment"] == "staging"
        and acceptance["result"] == "passed",
        "Invalid staging acceptance record",
    )

    require(
        acceptance["release"] == manifest,
        "Acceptance belongs to a different release",
    )

    require(
        acceptance["manifest_sha256"] == manifest_hash,
        "Accepted manifest checksum mismatch",
    )

    require(
        acceptance["deployed_at_epoch"]
        == state["deployed_at_epoch"],
        "Acceptance belongs to an earlier staging deployment",
    )

    require(
        acceptance["production_approval"] == "pending",
        "Unexpected staging acceptance authorization status",
    )

    expected_validation = {
        "runtime_and_security": ("assertions_passed", 44),
        "api_integration": ("assertions_passed", 51),
        "manual_ui": ("checks_passed", 9),
        "database_persistence": ("assertions_passed", 27),
    }

    for name, (counter, minimum) in expected_validation.items():

        validation = acceptance["validation"][name]

        require(
            validation["result"] == "passed"
            and type(validation[counter]) is int
            and validation[counter] >= minimum,
            f"Missing successful staging validation: {name}",
        )

    accepted_at = timestamp(acceptance["accepted_at"])

    require(
        int(accepted_at) == acceptance["accepted_at_epoch"],
        "Inconsistent staging acceptance timestamp",
    )

    require(
        state["deployed_at_epoch"] <= accepted_at <= time.time(),
        "Invalid staging acceptance chronology",
    )

    # Validate the evidence directory name before constructing
    # paths. This prevents path traversal through JSON data.
    evidence = acceptance["persistence_evidence"]

    directory = evidence["directory"]

    require(
        isinstance(directory, str)
        and re.fullmatch(
            r"persistence-test\.[A-Za-z0-9]{6}",
            directory,
        ) is not None,
        "Invalid persistence evidence directory",
    )

    expected_files = {
        "result.json",
        "staging-before.json",
        "staging-after.json",
        "development-before.json",
        "development-after.json",
        "infrastructure-before.json",
        "infrastructure-after.json",
    }

    require(
        set(evidence["sha256"]) == expected_files,
        "Incomplete persistence evidence",
    )

    for filename, checksum in evidence["sha256"].items():

        require(
            valid_sha256(checksum),
            "Invalid persistence evidence checksum",
        )

        path = root / "state" / directory / filename

        require(
            sha256_file(path) == checksum,
            f"Persistence evidence checksum mismatch: {filename}",
        )

    return {
        "manifest": manifest,
        "manifest_sha256": manifest_hash,
        "acceptance_sha256": acceptance_hash,
        "accepted_at": accepted_at,
    }


# ---------------------------------------------------------
# GitHub workflow execution verification
# ---------------------------------------------------------

def verify_run_metadata(
    run,
    workflow,
    run_id,
    local,
    now,
):
    """Verify exact workflow identity and execution metadata."""

    manifest = local["manifest"]

    expected_title = (
        "Production approval | "
        f"{manifest['release_tag']} | "
        f"{local['manifest_sha256']} | "
        f"{local['acceptance_sha256']}"
    )

    require(
        run["repository"]["id"] == REPOSITORY_ID
        and run["repository"]["owner"]["id"] == OWNER_ID
        and run["repository"]["full_name"] == REPOSITORY,
        "Untrusted authorization repository",
    )

    require(
        run["head_repository"]["id"] == REPOSITORY_ID,
        "Authorization originated from another repository",
    )

    require(
        str(run["id"]) == run_id,
        "Authorization run ID mismatch",
    )

    require(
        run["run_attempt"] == 1,
        "Authorization reruns are not permitted",
    )

    require(
        workflow["name"] == WORKFLOW_NAME
        and workflow["path"] == WORKFLOW_PATH
        and workflow["state"] == "active",
        "Untrusted or inactive authorization workflow",
    )

    require(
        run["workflow_id"] == workflow["id"]
        and run["name"] == WORKFLOW_NAME
        and run["path"] == WORKFLOW_PATH,
        "Authorization workflow identity mismatch",
    )

    require(
        run["event"] == "workflow_dispatch"
        and run["head_branch"] == "main",
        "Authorization must be manually dispatched from main",
    )

    require(
        run["status"] == "completed"
        and run["conclusion"] == "success",
        "Authorization workflow did not succeed",
    )

    require(
        run["display_title"] == expected_title,
        "Authorization release or checksum mismatch",
    )

    require(
        re.fullmatch(
            r"[0-9a-f]{40}",
            run["head_sha"],
        ) is not None,
        "Invalid authorization workflow commit",
    )

    created_at = timestamp(run["created_at"])

    updated_at = timestamp(run["updated_at"])

    require(
        local["accepted_at"] <= created_at <= updated_at <= now,
        "Authorization chronology is invalid",
    )

    require(
        now - created_at <= MAX_AUTHORIZATION_AGE,
        "Authorization has expired",
    )

    return created_at


def verify_workflow_source(content):
    """Verify the reviewed workflow at the execution commit."""

    require(
        content["type"] == "file"
        and content["path"] == WORKFLOW_PATH
        and content["encoding"] == "base64",
        "Unexpected workflow source response",
    )

    encoded = "".join(content["content"].split())

    raw = base64.b64decode(
        encoded,
        validate=True,
    )

    require(
        sha256_bytes(raw) == WORKFLOW_SHA256,
        "Authorization workflow source checksum mismatch",
    )


def verify_jobs(response, run_id, head_sha, created_at, now):
    """Require both expected jobs to complete successfully."""

    jobs = response["jobs"]

    require(
        response["total_count"] == 2
        and len(jobs) == 2,
        "Unexpected authorization job count",
    )

    require(
        {job["name"] for job in jobs} == EXPECTED_JOBS,
        "Unexpected authorization job identities",
    )

    by_name = {}

    for job in jobs:

        require(
            str(job["run_id"]) == run_id
            and job["head_sha"] == head_sha
            and job["run_attempt"] == 1,
            "Authorization job provenance mismatch",
        )

        require(
            job["status"] == "completed"
            and job["conclusion"] == "success",
            f"Authorization job failed: {job['name']}",
        )

        started = timestamp(job["started_at"])

        completed = timestamp(job["completed_at"])

        require(
            created_at <= started <= completed <= now,
            "Invalid authorization job chronology",
        )

        by_name[job["name"]] = (started, completed)

    validation = by_name["Validate Production Request"]

    authorization = by_name["Authorize Production Release"]

    require(
        validation[1] <= authorization[0],
        "Authorization job preceded request validation",
    )


# ---------------------------------------------------------
# Explicit human approval verification
# ---------------------------------------------------------

def verify_approval_history(approvals):
    """Require an explicit approval from the trusted reviewer."""

    require(
        isinstance(approvals, list),
        "Unexpected approval history response",
    )

    production_reviews = []

    for approval in approvals:

        environments = approval.get("environments", [])

        for environment in environments:

            if (
                environment.get("name") == "production"
                or environment.get("id")
                == PRODUCTION_ENVIRONMENT_ID
            ):

                require(
                    environment.get("name") == "production"
                    and environment.get("id")
                    == PRODUCTION_ENVIRONMENT_ID,
                    "Production environment identity mismatch",
                )

                production_reviews.append(approval)

                break

    # This project has exactly one required reviewer.
    # Reject ambiguous, rejected or repeated review histories.
    require(
        len(production_reviews) == 1,
        "Expected exactly one production approval",
    )

    approval = production_reviews[0]

    require(
        approval["state"] == "approved",
        "Production review did not approve deployment",
    )

    require(
        approval["user"]["id"] == REVIEWER_ID,
        "Production approval came from an untrusted reviewer",
    )


def verify_environment(environment):
    """Verify current production environment protection."""

    require(
        environment["id"] == PRODUCTION_ENVIRONMENT_ID
        and environment["name"] == "production",
        "Untrusted production environment",
    )

    rules = [
        rule
        for rule in environment["protection_rules"]
        if rule["type"] == "required_reviewers"
    ]

    require(
        len(rules) == 1,
        "Production reviewer protection is missing",
    )

    reviewers = rules[0]["reviewers"]

    require(
        len(reviewers) == 1
        and reviewers[0]["type"] == "User"
        and reviewers[0]["reviewer"]["id"] == REVIEWER_ID,
        "Unexpected production reviewer configuration",
    )

    policy = environment["deployment_branch_policy"]

    require(
        policy["protected_branches"] is False
        and policy["custom_branch_policies"] is True,
        "Production branch protection policy changed",
    )


def verify_branch_policy(response):
    """Require the production environment to allow only main."""

    policies = response["branch_policies"]

    require(
        response["total_count"] == 1
        and len(policies) == 1
        and policies[0]["name"] == "main"
        and policies[0].get("type") == "branch",
        "Production environment must permit only main",
    )


# ---------------------------------------------------------
# Replay protection
# ---------------------------------------------------------

def verify_not_consumed(run_id, root=ROOT):
    """Reject an authorization already consumed locally."""

    marker = (
        root
        / "state"
        / f"production-authorization-consumed-{run_id}.json"
    )

    require(
        not marker.exists() and not marker.is_symlink(),
        "Production authorization has already been consumed",
    )


# ---------------------------------------------------------
# Complete production authorization verification
# ---------------------------------------------------------

def verify_production_approval(
    manifest_path,
    run_id,
    root=ROOT,
    api=github_json,
):
    """Verify authorization without changing deployment state."""

    run_id = str(run_id)

    require(
        valid_run_id(run_id),
        "Invalid authorization run ID",
    )

    verify_not_consumed(run_id, root)

    local = verify_local_acceptance(manifest_path, root)

    print("PASS: Local staging acceptance verified")

    workflow = api(
        "/actions/workflows/production-approval.yml"
    )

    current = api(
        f"/actions/runs/{run_id}"
    )

    run = api(
        f"/actions/runs/{run_id}/attempts/1"
    )

    # Verify both the latest run metadata and exact attempt.
    # This prevents using an earlier successful attempt after
    # the workflow has subsequently been rerun.
    now = time.time()

    verify_run_metadata(
        current, workflow, run_id, local, now
    )

    created_at = verify_run_metadata(
        run, workflow, run_id, local, now
    )

    require(
        current["head_sha"] == run["head_sha"],
        "Current run and attempt commit mismatch",
    )

    print("PASS: Exact authorization run verified")

    source = api(
        f"/contents/{WORKFLOW_PATH}?ref={run['head_sha']}"
    )

    verify_workflow_source(source)

    print("PASS: Reviewed workflow source verified")

    jobs = api(
        f"/actions/runs/{run_id}/attempts/1/jobs"
        "?per_page=100"
    )

    verify_jobs(
        jobs,
        run_id,
        run["head_sha"],
        created_at,
        time.time(),
    )

    print("PASS: Both authorization jobs verified")

    approvals = api(
        f"/actions/runs/{run_id}/approvals"
    )

    verify_approval_history(approvals)

    print("PASS: Explicit production approval verified")

    environment = api(
        "/environments/production"
    )

    verify_environment(environment)

    branch_policy = api(
        "/environments/production/deployment-branch-policies"
        "?per_page=100"
    )

    verify_branch_policy(branch_policy)

    print("PASS: Production environment protection verified")

    # Recheck the latest run after reading approval history.
    latest = api(f"/actions/runs/{run_id}")

    verify_run_metadata(
        latest, workflow, run_id, local, time.time()
    )

    require(
        latest["head_sha"] == run["head_sha"],
        "Authorization run changed during verification",
    )

    verify_not_consumed(run_id, root)

    print("PASS: Authorization freshness and replay check")

    return {
        "schema_version": 1,
        "result": "passed",
        "environment": "production",
        "approval_run_id": run_id,
        "approval_run_attempt": 1,
        "approval_workflow_commit": run["head_sha"],
        "approval_workflow_sha256": WORKFLOW_SHA256,
        "reviewer_id": REVIEWER_ID,
        "production_environment_id": PRODUCTION_ENVIRONMENT_ID,
        "release_tag": local["manifest"]["release_tag"],
        "release_commit": local["manifest"]["commit_sha"],
        "manifest_sha256": local["manifest_sha256"],
        "acceptance_sha256": local["acceptance_sha256"],
        "verified_at_epoch": int(time.time()),
        "expires_at_epoch": int(
            created_at + MAX_AUTHORIZATION_AGE
        ),
    }


# ---------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Verify production release authorization"
    )

    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Path to the accepted release manifest",
    )

    parser.add_argument(
        "--run-id",
        required=True,
        help="GitHub production approval workflow run ID",
    )

    args = parser.parse_args()

    try:

        result = verify_production_approval(
            args.manifest,
            args.run_id,
        )

    except Exception as error:

        # Fail closed on malformed data, unavailable APIs,
        # missing files or failed security conditions.
        print(
            f"PRODUCTION AUTHORIZATION REJECTED: {error}",
            file=sys.stderr,
        )

        return 1

    print(json.dumps(result, indent=2, sort_keys=True))

    print("PRODUCTION AUTHORIZATION VERIFIED")

    print("No deployment or authorization consumption performed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
