# Architecture decision record — Phase 1

## ADR-001: Monorepo
**Decision:** Keep frontend, backend, deployment, and documentation in one GitHub repository.
**Why:** A single pull request can validate a complete application change and its deployment configuration.
**Tradeoff:** CI must separate frontend and backend tasks to avoid unnecessarily long checks.

## ADR-002: Local staging and production
**Decision:** Use separate Compose projects, ports, volumes and credentials on the same development machine.
**Why:** Meets the assignment's local execution allowance without paying for AWS compute.
**Risk:** The host remains a single point of failure; these are demonstration environments, not production-grade availability.

## ADR-003: AWS ECR only for cloud registry
**Decision:** Build and push frontend/backend container images to AWS ECR using GitHub Actions and OIDC.
**Why:** Meets the required ECR delivery step without storing long-lived AWS access keys.
**Dependency:** Requires AWS account and IAM OIDC trust configuration in Phase 5.

## ADR-004: Self-hosted deployment runner
**Decision:** Use a dedicated self-hosted GitHub Actions runner in WSL2 for local Compose deployments.
**Why:** GitHub-hosted runners cannot access private Docker Desktop services on the user's machine by default.
**Security:** Never execute untrusted pull-request code on this runner. Restrict deployment jobs to trusted protected branches/environments; isolate its credentials and Docker access. Docker access effectively grants host-level privileges.

## ADR-005: Production promotion
**Decision:** Promote the exact tested image digest after explicit manual approval.
**Why:** Rebuilding after staging could deploy different artifacts.
**Dependency:** Check GitHub Environment reviewer availability for the chosen repository plan; otherwise implement an auditable manual dispatch approval gate.
