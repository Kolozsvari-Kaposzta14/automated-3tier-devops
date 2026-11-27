"""Validate release metadata before local deployment.

This module treats release manifests as untrusted data.
It does not execute commands, contact AWS, or start containers.

Structural validation does not establish release authorization.
Authorization must be verified separately against GitHub.
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Restrict deployments to our explicitly approved AWS registry.
REGISTRY = "492052863115.dkr.ecr.eu-central-1.amazonaws.com"

REPOSITORIES = {
    "backend": "three-tier-backend",
    "frontend": "three-tier-frontend",
    "nginx": "three-tier-nginx",
}

EXPECTED_FIELDS = {
    "schema_version",
    "commit_sha",
    "release_tag",
    "run_id",
    "run_attempt",
    "platform",
    "registry",
    "images",
}

# Prevent excessively large release metadata files.
MAX_MANIFEST_BYTES = 65536


def require(condition, message):
    """Stop validation immediately when a requirement fails."""
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    """Reject ambiguous JSON objects containing duplicate keys."""
    result = {}

    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value

    return result


def matches(pattern, value):
    """Validate both the value type and its exact format."""
    return isinstance(value, str) and (
        re.fullmatch(pattern, value) is not None
    )


def validate_manifest(path):
    """Return validated release metadata or raise an error."""

    # Read a bounded amount of data.
    # Never execute anything contained in the manifest.
    with Path(path).open("rb") as file:
        raw = file.read(MAX_MANIFEST_BYTES + 1)

    require(
        len(raw) <= MAX_MANIFEST_BYTES,
        "Manifest exceeds maximum permitted size",
    )

    manifest = json.loads(
        raw,
        object_pairs_hook=unique_object,
    )

    require(
        isinstance(manifest, dict),
        "Manifest must be a JSON object",
    )

    require(
        set(manifest) == EXPECTED_FIELDS,
        "Unexpected or missing manifest fields",
    )

    require(
        type(manifest["schema_version"]) is int
        and manifest["schema_version"] == 1,
        "Unsupported manifest schema",
    )

    require(
        manifest["registry"] == REGISTRY,
        "Registry is not approved",
    )

    require(
        manifest["platform"] == "linux/amd64",
        "Unsupported release platform",
    )

    # Validate the Git commit and GitHub workflow identifiers.
    commit = manifest["commit_sha"]
    run_id = manifest["run_id"]
    attempt = manifest["run_attempt"]

    require(
        matches(r"[a-f0-9]{40}", commit),
        "Invalid Git commit SHA",
    )

    require(
        matches(r"[1-9][0-9]{0,19}", run_id),
        "Invalid workflow run ID",
    )

    require(
        matches(r"[1-9][0-9]{0,9}", attempt),
        "Invalid workflow run attempt",
    )

    # Reconstruct the expected immutable release tag.
    expected_tag = f"sha-{commit[:12]}-{run_id}-{attempt}"

    require(
        manifest["release_tag"] == expected_tag,
        "Release tag does not match release metadata",
    )

    images = manifest["images"]

    require(
        isinstance(images, dict)
        and set(images) == set(REPOSITORIES),
        "Unexpected or missing image components",
    )

    # Validate each image against its approved repository.
    for component, repository in REPOSITORIES.items():
        image = images[component]

        require(
            isinstance(image, dict)
            and set(image) == {
                "repository",
                "digest",
                "reference",
            },
            f"Invalid {component} image fields",
        )

        require(
            image["repository"] == repository,
            f"Unapproved {component} repository",
        )

        digest = image["digest"]

        require(
            matches(r"sha256:[a-f0-9]{64}", digest),
            f"Invalid {component} image digest",
        )

        # Reconstruct the image reference rather than trusting
        # an arbitrary registry or reference from the manifest.
        expected_reference = (
            f"{REGISTRY}/{repository}@{digest}"
        )

        require(
            image["reference"] == expected_reference,
            f"Invalid {component} image reference",
        )

    return manifest


def main():
    """Provide a read-only command-line validation interface."""
    parser = argparse.ArgumentParser(
        description="Validate an immutable application release."
    )

    parser.add_argument(
        "manifest",
        type=Path,
        help="Path to release-manifest.json",
    )

    args = parser.parse_args()

    try:
        manifest = validate_manifest(args.manifest)

    except (OSError, ValueError, RecursionError):
        # Do not echo arbitrary untrusted manifest contents.
        print(
            "FAIL: Release manifest rejected.",
            file=sys.stderr,
        )
        return 1

    print("PASS: Release manifest structure validated")
    print(f"Release: {manifest['release_tag']}")
    print(f"Commit: {manifest['commit_sha']}")
    print(f"Workflow run: {manifest['run_id']}")
    print(f"Run attempt: {manifest['run_attempt']}")

    for component in REPOSITORIES:
        print(
            f"{component}: "
            f"{manifest['images'][component]['reference']}"
        )

    print("NOTE: Release authorization is not yet verified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
