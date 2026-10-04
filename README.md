# football-engine

## Structure

| Folder | Purpose |
| --- | --- |
| `shared/` | Code and utilities shared across modules |
| `0001/` – `0005/` | Individual modules |
| `.github/workflows/` | GitHub Actions workflows |

## Secrets

Never commit API keys or other secrets. Keep them in a local `.env` file (ignored by git) or in GitHub Actions secrets (Settings → Secrets and variables → Actions).
