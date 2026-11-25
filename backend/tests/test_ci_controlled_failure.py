"""Temporary test used to validate CI failure handling.

This test intentionally fails to demonstrate:
1. Automated test failure detection.
2. GitHub Actions failure propagation.
3. Automatic pull request failure notification.
4. Branch protection and merge prevention.

This file must be removed after the experiment.
"""


def test_controlled_ci_failure():
    """Simulate a deterministic test failure."""
    assert False, "Intentional CI failure for branch protection validation"
