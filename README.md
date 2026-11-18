# Automated Lifecycle for 3-Tier Web Apps

Senior DevOps engineering learning project. **Phase 1: repository foundation.**

## Planned architecture
React + TypeScript frontend → Nginx reverse proxy → FastAPI backend → PostgreSQL database.
GitHub Actions will validate pull requests and publish images to AWS ECR; a local self-hosted runner will deploy staging and production Docker Compose stacks in later phases.

## Current status
Only the repository foundation is implemented. No runnable application, Docker images, CI/CD pipeline, AWS resources, or production approval mechanism exists yet.

## Prerequisites
- Git
- Docker Desktop with WSL2 integration (Windows), or Docker Engine with Compose plugin (Linux)
- Node.js 22 LTS and Python 3.12 for optional host-based development
- GitHub account; AWS account for later ECR setup

## Getting started
```bash
# Confirm Git is installed and available.
git --version
# Confirm Docker CLI can contact the running Docker engine.
docker info
# Confirm the Compose plugin is available.
docker compose version
# Initialize the repository (only once).
git init -b development
# Stage only tracked project files; .gitignore excludes local secrets.
git add .
# Save the initial foundation commit.
git commit -m "chore: initialize three-tier DevOps project"
```

Create a **private** GitHub repository, then add it as `origin` and push the development branch. Replace the placeholder URL with your own repository URL:
```bash
# Point the local repository at the GitHub repository you created.
git remote add origin https://github.com/YOUR-USERNAME/automated-3tier-devops.git
# Upload the foundation branch and set upstream tracking.
git push -u origin development
```

Create `main` as the protected integration branch in GitHub before configuring CI. Later, open pull requests from `development` into `main`. Do not configure mandatory checks until those checks actually exist.

## Secrets and environment variables
Copy `.env.example` to `.env` only when we configure Compose. Never commit `.env`, AWS credentials, or tokens. Replace all placeholder credentials with locally generated values.

## Directory map
- `frontend/`: React + TypeScript application (Phase 2)
- `backend/`: FastAPI application and tests (Phase 2)
- `infrastructure/nginx/`: reverse proxy (Phase 3)
- `infrastructure/compose/`: isolated local staging and production (Phase 3+)
- `infrastructure/terraform/`: optional AWS ECR/IAM provisioning (Phase 5)
- `.github/workflows/`: CI/CD workflows (Phases 4 and 6)
- `scripts/`: deployment, verification and rollback scripts (Phase 6)
- `docs/`: architecture decisions, report and screenshots

See `docs/architecture/decisions.md` and `docs/phase-1-validation.md` for rationale and validation.
