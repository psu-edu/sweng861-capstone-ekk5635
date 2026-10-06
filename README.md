# CoverageDesk

*Tells you what shape a public company is in — in terms that are easy to understand.*

CoverageDesk lets a signed-in user register a **coverage**: a public company they are tracking, identified by its SEC CIK. For each coverage the service collects the company's reported figures from the SEC EDGAR API, computes a few indicators (revenue growth, net margin, equity ratio), and asks an LLM to word them in plain language. The summary is stored with the filings the figures came from, so every number can be checked against its source.

**Author:** Eungchan Kang (`ekk5635`)
**Course:** SWENG 861 – Software Construction
**Project Category:** Project V — Bring Your Own Domain (approved by instructor, 2026-09-01)

## Features

- Google sign-in (OIDC, authorization code flow with PKCE); the service then issues its own short-lived JWT.
- Coverage CRUD, scoped to the owner: another user's coverage answers 404.
- Two roles: **user** (own coverages) and **admin** (read-only view of all coverages via `/api/admin/coverages`).
- Financial figures collected from the SEC EDGAR `companyconcept` API and stored per period.
- Plain-language summary generated on request by an OpenAI-compatible LLM, stored with its indicators and source filings.
- Health, readiness, and liveness endpoints; JSON request logs with a request ID; Prometheus metrics and a Grafana dashboard with SLO alerts.

## Tech Stack

| Layer | Choice |
| :--- | :--- |
| Frontend | Vue 3, Vite, TypeScript, Vue Router |
| Backend | FastAPI (Python 3.14), SQLAlchemy, Alembic |
| Database | PostgreSQL 17 |
| Authentication | Google OAuth 2.0 / OIDC, JWT session tokens, role check per request |
| External API | SEC EDGAR `companyconcept` (XBRL financial data, one concept per request) |
| LLM | Any OpenAI-compatible endpoint, set in `.env`; currently OpenAI `gpt-4o-mini` |
| Testing | pytest (server), Vitest with Vue Test Utils (client) |
| Containers & CI | Multi-stage Docker builds, Docker Compose, nginx gateway, GitHub Actions |
| Observability | Structured JSON logging, Prometheus, Grafana |

Design decisions and diagrams: [`docs/architecture.md`](docs/architecture.md) and [`docs/adr/`](docs/adr/).

## Repository Structure

| Folder | Purpose |
| :--- | :--- |
| `.github/workflows` | CI: lint, tests, dependency audit, image build and scan, alert rule tests |
| `docs` | Architecture diagrams and decision records |
| `src/server` | FastAPI service, Alembic migrations, and server tests (`src/server/tests`) |
| `src/client` | Vue single-page app and client tests (`src/client/src/__tests__`) |
| `ops/docker` | Dockerfiles, `docker-compose.yml`, nginx gateway config |
| `ops/observability` | Prometheus config, alert rules and their tests, Grafana provisioning |

## Credentials and Configuration

No secret is committed. All settings live in `src/server/.env`, which is git-ignored:

```bash
cp src/server/.env.example src/server/.env
```

Then fill in:

| Setting | Where it comes from |
| :--- | :--- |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Cloud Console → Credentials → OAuth client ID (Web application) |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/auth/callback`, registered on that client exactly |
| `SESSION_JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | Any local values; `DATABASE_URL` must use the same three |
| `SEC_USER_AGENT` | `"<project name> <your email>"` — EDGAR has no API key but rejects requests without a contact |
| `LLM_API_KEY` (+ `LLM_BASE_URL`, `LLM_MODEL`) | Optional. Leave the key empty to run without summaries; the summary endpoint then answers 503 |
| `TEST_DATABASE_URL` | A separate database for tests (see [Running the Tests](#running-the-tests)) |

## How to Run

### With Docker Compose (recommended)

Requires Docker. From the repository root:

```bash
docker compose --env-file src/server/.env -f ops/docker/docker-compose.yml up -d --build
```

`--env-file` is required: Compose reads the database credentials from it. The `migrate` service applies the Alembic migrations before the API starts.

| URL | What |
| :--- | :--- |
| http://localhost:8000 | The app (nginx gateway: the SPA, `/api`, `/auth`, `/health`) |
| http://localhost:8000/docs | OpenAPI (Swagger UI) |
| http://localhost:8000/health/ready | Readiness, including the database |
| http://localhost:3000 | Grafana dashboard (bound to localhost) |
| http://localhost:9090 | Prometheus (bound to localhost) |
| `localhost:5432` | PostgreSQL, published for local tools and the test database |

Stop with `docker compose -f ops/docker/docker-compose.yml down` (add `-v` to delete the database volume).

### Without Docker (development)

Requires Python 3.14, Node 22, and a running PostgreSQL that matches `DATABASE_URL` (for example, only the `db` service from Compose). Each block starts from the repository root.

The server's virtual environment is also what the sample-data scripts and the server tests below use, so create it even if you run the app with Docker:

```bash
cd src/server
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Server, on http://localhost:8000:

```bash
cd src/server
.venv/bin/alembic upgrade head
.venv/bin/uvicorn main:app --reload
```

Client, on http://localhost:5173 (proxies `/api` and `/auth` to :8000):

```bash
cd src/client
npm ci
npm run dev
```

Keep `FRONTEND_URL=http://localhost:5173` from `.env.example` so the login callback returns to the Vite server. (Compose overrides it to `http://localhost:8000` for its own API container.)

### Using the App

1. Open the app and sign in with Google. The first sign-in creates your user with the `user` role.
2. Create a coverage with a real CIK, for example Apple: ticker `AAPL`, CIK `0000320193`.
3. On the coverage page, select **Collect financials**, then **Generate summary**. Each source filing links to its folder on SEC EDGAR.

To make your account an admin, change its role in the database:

```bash
docker exec -it coveragedesk-db psql -U <POSTGRES_USER> -d <POSTGRES_DB> \
  -c "UPDATE users SET role = 'admin' WHERE email = '<your email>';"
```

### Sample Data

`src/server/seed_demo.py` puts the database into a fixed demo state: two analysts and an admin, five coverages with real CIKs, and a session token for each account printed to the terminal.

> **Warning:** it first truncates `users` and `coverages` with `CASCADE`, which also empties `coverage_financials` and `coverage_summaries`. Accounts created by Google sign-in and any generated summaries are deleted.

Needs the server's virtual environment (see [Without Docker](#without-docker-development)) and the database running:

```bash
cd src/server && .venv/bin/python seed_demo.py
```

`demo_walkthrough.py` reseeds and prints a CRUD and tenancy transcript (create, read, update, delete, and a cross-tenant 404).

## Running the Tests

### Server (pytest)

Database tests need a separate database so they never touch demo data. With the Compose `db` running:

```bash
docker exec -i coveragedesk-db psql -U <POSTGRES_USER> -d postgres \
  -c "CREATE DATABASE coveragedesk_test OWNER <POSTGRES_USER>;"
```

`.env.example` already points `TEST_DATABASE_URL` at `coveragedesk_test`; make sure its user and password match `POSTGRES_USER` and `POSTGRES_PASSWORD`. Then, with the server's virtual environment (see [Without Docker](#without-docker-development)):

```bash
cd src/server
.venv/bin/ruff check .
.venv/bin/pytest --cov=.
```

Without `TEST_DATABASE_URL` the database tests skip and coverage falls below the 80% gate in `.coveragerc`.

### Client (Vitest)

```bash
cd src/client
npm run lint
npm run test:coverage   # fails below 80% lines, statements, branches, or functions
npm run build           # type-check and production build
```

`npm run test:integration` runs the specs in `src/__tests__/integration` against a running backend.

### CI

`.github/workflows/ci.yml` runs on every push and pull request: `backend` (ruff, pytest with a Postgres service), `frontend` (lint, coverage, build), `audit` (pip-audit, npm audit, tracked `.env` check), `alert-rules` (promtool), and `package` (builds both images, smoke-tests them, checks they run as non-root, and scans them with Trivy).

GitHub Actions is disabled for the `psu-edu` organization, so the workflow runs on a personal mirror of this repository: [yeschan119/sweng861-capstone-ekk5635 Actions](https://github.com/yeschan119/sweng861-capstone-ekk5635/actions).

## AI Usage

An AI coding assistant (Claude Code) was used to draft code, tests, configuration, and documentation. The author reviewed, edited, and tested every change one piece at a time before committing it, and is responsible for its content. A reflection on AI use is in the final slides.

---
*This repository is for academic use. No secrets or API keys are committed; see `.gitignore` and `src/server/.env.example`.*
