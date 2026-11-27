"""Controlled, on-demand staging deployment.

Only reviewed local code and configuration are executed.
Release manifests are treated strictly as structured data.

Production deployment is deliberately disabled until
the production approval mechanism is implemented.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


# ---------------------------------------------------------
# Fixed deployment configuration
# ---------------------------------------------------------

ROOT = Path.home() / ".local/share/automated-3tier-deploy"
BIN = ROOT / "bin"

CONFIG_ROOT = (
    Path.home() / ".config/automated-3tier-devops"
)

ACCOUNT = "492052863115"
REGION = "eu-central-1"

REGISTRY = (
    f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"
)

# A dedicated local pull-only role will be created next.
# Administrative AWS identities are not accepted.
AWS_PROFILE = "devops-deploy"
AWS_ROLE = "LocalThreeTierECRPull"

COMPOSE = ROOT / "compose.deploy.yaml"

TRUSTED_FILES = {
    COMPOSE:
        "4e390608f0bf9e583c323d6b6eff5f6d276fa775e72f4469e9e8c7e636577aca",
    BIN / "validate_release.py":
        "43c27775b9a9b4b20c6d4036c8f3af1122f258f10a32b4c22e4dfcb7a493029f",
    BIN / "verify_github_release.py":
        "0e79fee23039b125f809d2995d04c24cec8e1815d4002d05d2540ca8809e70a2",
}


def require(condition, message):
    """Fail closed when a security requirement is not met."""
    if not condition:
        raise RuntimeError(message)


def verify_private_file(path):
    """Verify ownership, file type and permissions."""

    metadata = path.lstat()

    require(
        stat.S_ISREG(metadata.st_mode),
        "Expected a regular private file",
    )

    require(
        metadata.st_uid == os.getuid(),
        "Unexpected private file owner",
    )

    require(
        stat.S_IMODE(metadata.st_mode) == 0o600,
        "Unexpected private file permissions",
    )


def verify_trusted_files():
    """Reject modifications to the reviewed local files."""

    for path, expected in TRUSTED_FILES.items():
        verify_private_file(path)

        actual = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

        require(
            actual == expected,
            f"Trusted file integrity failure: {path.name}",
        )

        print(f"PASS: Trusted file {path.name}")


def run_command(
    command,
    *,
    env=None,
    capture=False,
    input_data=None,
    timeout=120,
):
    """Execute explicit argument lists without a shell."""

    result = subprocess.run(
        command,
        env=env,
        input=input_data,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        timeout=timeout,
        check=True,
    )

    return result.stdout


def aws_environment():
    """Avoid inherited AWS credential and endpoint overrides."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("AWS_")
    }

    environment.update({
        "AWS_PROFILE": AWS_PROFILE,
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
        "AWS_PAGER": "",
        "AWS_CLI_AUTO_PROMPT": "off",
        "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
        "AWS_EC2_METADATA_DISABLED": "true",
    })

    return environment


def aws_command(*arguments):
    """Execute AWS CLI using the dedicated deployment profile."""

    return run_command(
        [
            "/usr/bin/aws",
            "--profile", AWS_PROFILE,
            "--region", REGION,
            "--no-cli-pager",
            *arguments,
        ],
        env=aws_environment(),
        capture=True,
    )


def aws_json(*arguments):
    """Parse AWS responses as JSON data."""

    return json.loads(
        aws_command(*arguments, "--output", "json")
    )


def verify_aws_identity():
    """Require the dedicated assumed pull-only role."""

    identity = aws_json(
        "sts", "get-caller-identity"
    )

    expected_prefix = (
        f"arn:aws:sts::{ACCOUNT}:"
        f"assumed-role/{AWS_ROLE}/"
    )

    require(
        identity.get("Account") == ACCOUNT,
        "Unexpected AWS account",
    )

    require(
        identity.get("Arn", "").startswith(
            expected_prefix
        ),
        "Dedicated pull-only AWS role required",
    )

    print("PASS: Dedicated AWS deployment identity")


def verify_ecr_images(manifest):
    """Compare every manifest digest with its ECR release tag."""

    for component, image in manifest["images"].items():

        response = aws_json(
            "ecr", "describe-images",
            "--registry-id", ACCOUNT,
            "--repository-name", image["repository"],
            "--image-ids",
            f"imageTag={manifest['release_tag']}",
        )

        details = response.get("imageDetails", [])

        require(
            len(details) == 1,
            f"Unexpected ECR result for {component}",
        )

        detail = details[0]

        require(
            detail.get("imageDigest") == image["digest"],
            f"ECR digest mismatch for {component}",
        )

        require(
            manifest["release_tag"]
            in detail.get("imageTags", []),
            f"ECR release tag mismatch for {component}",
        )

        require(
            detail.get("repositoryName")
            == image["repository"],
            f"ECR repository mismatch for {component}",
        )

        require(
            detail.get("registryId") == ACCOUNT,
            f"ECR registry mismatch for {component}",
        )

        print(f"PASS: ECR digest verified for {component}")


def compose_environment(manifest):
    """Build a controlled environment for Docker Compose."""

    # Do not inherit Docker context, Compose project,
    # image, database or port overrides.
    environment = {
        key: os.environ[key]
        for key in ("HOME", "PATH", "USER", "LANG")
        if key in os.environ
    }

    for component, image in manifest["images"].items():
        environment[
            f"{component.upper()}_IMAGE"
        ] = image["reference"]

    return environment


def compose_command(env_file):
    """Construct the fixed staging Compose command."""

    return [
        "/usr/bin/docker",
        "compose",
        "--project-name", "automated-3tier-staging",
        "--project-directory", str(ROOT),
        "--env-file", str(env_file),
        "-f", str(COMPOSE),
    ]


def verify_staging_credentials(path):
    """Validate the expected private environment file."""

    verify_private_file(path)

    values = {}

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        key, separator, value = line.partition("=")

        require(
            separator == "=" and key not in values,
            "Invalid staging environment file",
        )

        values[key] = value

    require(
        set(values) == {
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "HTTP_PORT",
        },
        "Unexpected staging environment variables",
    )

    require(
        values["POSTGRES_DB"] == "taskmanager"
        and values["POSTGRES_USER"] == "taskapp"
        and values["HTTP_PORT"] == "8082",
        "Unexpected staging configuration",
    )

    require(
        re.fullmatch(
            r"[A-Za-z0-9_-]{43}",
            values["POSTGRES_PASSWORD"],
        ) is not None,
        "Invalid staging password format",
    )

    print("PASS: Staging environment configuration")


def pull_and_deploy(manifest, env_file):
    """Authenticate, pull verified images and deploy staging."""

    environment = compose_environment(manifest)
    compose = compose_command(env_file)

    # Validate Compose without displaying resolved secrets.
    run_command(
        compose + ["config", "--quiet"],
        env=environment,
    )

    # Keep ECR authentication outside the normal Docker
    # configuration and remove it after the operation.
    with tempfile.TemporaryDirectory(
        prefix="docker-auth-",
        dir=ROOT,
    ) as docker_config:

        environment["DOCKER_CONFIG"] = docker_config

        # Do not print or persist the raw ECR login token.
        password = aws_command(
            "ecr", "get-login-password"
        )

        try:
            run_command(
                [
                    "/usr/bin/docker", "login",
                    "--username", "AWS",
                    "--password-stdin", REGISTRY,
                ],
                env=environment,
                input_data=password,
                capture=True,
            )

            print("PASS: Temporary ECR authentication")

            # Pull the exact application digests and the
            # configured PostgreSQL base image.
            run_command(
                compose + ["pull"],
                env=environment,
                timeout=600,
            )

            # Never build locally or pull a different image
            # implicitly during container creation.
            run_command(
                compose + [
                    "up", "-d",
                    "--no-build",
                    "--pull", "never",
                    "--wait",
                    "--wait-timeout", "120",
                ],
                env=environment,
                timeout=240,
            )

        finally:
            # Remove the temporary registry login even if
            # pulling or deployment fails.
            del password

            try:
                run_command(
                    [
                        "/usr/bin/docker",
                        "logout",
                        REGISTRY,
                    ],
                    env=environment,
                    capture=True,
                    timeout=30,
                )
            except (
                subprocess.SubprocessError,
                OSError,
            ):
                print(
                    "WARNING: Docker logout failed; "
                    "temporary configuration will be removed."
                )


def verify_application():
    """Wait for frontend and database-backed API readiness."""

    base_url = "http://127.0.0.1:8082"

    # Avoid routing localhost health requests through
    # an inherited HTTP proxy.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({})
    )

    for attempt in range(30):

        try:
            with opener.open(
                base_url + "/api/health",
                timeout=5,
            ) as response:

                health = json.loads(
                    response.read(65536)
                )

                require(
                    response.status == 200
                    and health.get("status") == "ok",
                    "Backend is not ready",
                )

            with opener.open(
                base_url + "/",
                timeout=5,
            ) as response:

                require(
                    response.status == 200,
                    "Frontend is not ready",
                )

            print("PASS: Backend health endpoint")
            print("PASS: Frontend HTTP endpoint")
            return

        except (
            OSError,
            ValueError,
            RuntimeError,
        ):
            time.sleep(2)

    raise RuntimeError(
        "Application readiness checks timed out"
    )


def record_state(manifest):
    """Record the deployed release using an atomic file update."""

    destination = ROOT / "state/staging.json"

    state = {
        "environment": "staging",
        "release": manifest,
        "readiness": "passed",
        "integration_tests": "pending",
        "deployed_at_epoch": int(time.time()),
    }

    # Write a temporary file before replacing the state.
    # This avoids partially written deployment records.
    fd, temporary = tempfile.mkstemp(
        prefix="staging-",
        suffix=".json",
        dir=destination.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(state, file, indent=2)
            file.write("\n")

        os.replace(temporary, destination)

    finally:
        Path(temporary).unlink(missing_ok=True)

    print("PASS: Staging deployment state recorded")


def main():
    parser = argparse.ArgumentParser(
        description="Controlled staging release deployment."
    )

    parser.add_argument(
        "manifest",
        type=Path,
        help="Path to release-manifest.json",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly authorize staging deployment",
    )

    args = parser.parse_args()

    os.umask(0o077)

    try:
        # Verify local code before importing the validator.
        verify_trusted_files()

        sys.path.insert(0, str(BIN))

        from validate_release import validate_manifest

        env_file = CONFIG_ROOT / "staging.env"

        verify_staging_credentials(env_file)

        # Serialize deployments so two invocations cannot
        # modify the staging environment simultaneously.
        with (ROOT / "state/deploy.lock").open("a") as lock:

            fcntl.flock(
                lock,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

            # Take a private snapshot of the external manifest.
            # All subsequent checks use the same snapshot.
            with tempfile.TemporaryDirectory(
                prefix="release-check-",
                dir=ROOT,
            ) as temporary:

                snapshot = (
                    Path(temporary) / "release-manifest.json"
                )

                with args.manifest.open("rb") as source:
                    raw = source.read(65537)

                require(
                    len(raw) <= 65536,
                    "Release manifest is too large",
                )

                snapshot.write_bytes(raw)

                manifest = validate_manifest(snapshot)

                print(
                    f"Release: {manifest['release_tag']}"
                )

                # Reuse the trusted GitHub verifier.
                run_command(
                    [
                        sys.executable,
                        "-B",
                        str(BIN / "verify_github_release.py"),
                        str(snapshot),
                    ],
                    timeout=120,
                )

                verify_aws_identity()
                verify_ecr_images(manifest)

                # Default mode is read-only verification.
                # Actual deployment requires --execute.
                if not args.execute:
                    print(
                        "PRECHECK PASSED: "
                        "No containers deployed."
                    )
                    return 0

                # Require explicit release-specific confirmation.
                print()
                print("Target: staging")
                print("URL: http://127.0.0.1:8082")

                confirmation = input(
                    "Type the exact release tag to deploy: "
                )

                require(
                    confirmation == manifest["release_tag"],
                    "Deployment confirmation rejected",
                )

                # Invalidate any previous success record
                # before changing the running environment.
                (ROOT / "state/staging.json").unlink(
                    missing_ok=True
                )

                pull_and_deploy(manifest, env_file)

                verify_application()
                record_state(manifest)

                print()
                print("STAGING DEPLOYMENT COMPLETED")
                print("Integration testing remains required.")

    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        EOFError,
    ) as error:

        # Avoid printing subprocess output or exception
        # details that could contain sensitive information.
        print(
            f"FAIL: Deployment stopped "
            f"({type(error).__name__}).",
            file=sys.stderr,
        )

        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
