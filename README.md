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
Store actual environment files outside the Git repository,
preferably on the native Linux filesystem when using WSL.

Create a private configuration directory:

```bash
mkdir -p "$HOME/.config/automated-3tier-devops"
chmod 700 "$HOME/.config/automated-3tier-devops"
```

For a fresh installation, create private environment files
from the corresponding public templates:

```bash
cp -n .env.example \
    "$HOME/.config/automated-3tier-devops/primary.env"

cp -n infrastructure/compose/.env.example \
    "$HOME/.config/automated-3tier-devops/legacy.env"

chmod 600 "$HOME/.config/automated-3tier-devops/primary.env"
chmod 600 "$HOME/.config/automated-3tier-devops/legacy.env"
```

Replace placeholder passwords with strong, unique,
locally generated values before starting the environments.

Use URL-safe characters for the primary PostgreSQL password
because it is interpolated into the backend database URL.

Do not overwrite existing credentials or change passwords for
initialized PostgreSQL volumes without coordinating password rotation.

Start the primary three-tier application:

```bash
env -u POSTGRES_PASSWORD docker compose \
    --env-file "$HOME/.config/automated-3tier-devops/primary.env" \
    up -d --build
```

If the optional standalone PostgreSQL environment is needed,
start it separately:

```bash
env -u LEGACY_POSTGRES_PASSWORD docker compose \
    --project-name compose \
    --env-file "$HOME/.config/automated-3tier-devops/legacy.env" \
    -f infrastructure/compose/compose.database.yml \
    up -d
```

Never commit actual environment files, database passwords,
AWS credentials, or authentication tokens.


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
