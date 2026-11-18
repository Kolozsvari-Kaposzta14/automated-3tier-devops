# Phase 1 validation checklist

## Repository
- [ ] All directories and tracked `.gitkeep` placeholders are present.
- [ ] `git status` shows no uncommitted files after the initial commit.
- [ ] `.env` is excluded by `.gitignore` (`git check-ignore .env`).
- [ ] `git remote -v` points to the intended GitHub repository.
- [ ] The `development` branch has been pushed successfully.

## Development machine
- [ ] `git --version` succeeds.
- [ ] `docker info` succeeds (Docker engine running).
- [ ] `docker compose version` succeeds.
- [ ] WSL2 integration works if using Docker Desktop on Windows.

## Future phases (NOT YET COMPLETE)
- [ ] React frontend and FastAPI backend run.
- [ ] PostgreSQL persists data.
- [ ] Nginx routes frontend/API requests.
- [ ] Pull-request CI passes and failure comments work.
- [ ] Images are pushed to ECR.
- [ ] Staging deploy and tests pass.
- [ ] Production promotion is explicitly approved.

Record command output and screenshots under `docs/evidence/` only after actually running them.
