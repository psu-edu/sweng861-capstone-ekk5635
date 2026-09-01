# CoverageDesk

*Track the companies you follow — the app reads their SEC filings for you.*

CoverageDesk lets a user register a **coverage**: a company they are tracking, together with the reason they care about it and the conditions they want to watch. The application then pulls that company's financial facts and disclosure events from the SEC EDGAR API and turns them into a readable analysis. The goal is that the user gains insight without reading hundreds of pages of regulatory filings.

**Author:** Eungchan Kang (`ekk5635`)
**Course:** SWENG 861 – Software Construction
**Project Category:** Project V — Bring Your Own Domain (approved by instructor, 2026-09-01)

---

## Current Status

**Week 2 — Deliverable I: Proposal & Checkpoint.**
This repository is initialized with the required structure and project information. No application code has been committed yet; implementation starts in Week 3.

## Planned Tech Stack

| Layer | Choice |
| :--- | :--- |
| Frontend | Next.js (React) |
| Backend | FastAPI (Python) |
| Database | PostgreSQL |
| Authentication | OAuth 2.0 / OIDC social login, JWT session tokens |
| External API | SEC EDGAR `companyfacts` (XBRL financial data) |
| LLM | DRIFT inference server provided for this course |
| Containers & CI | Docker Compose, GitHub Actions |

## Repository Structure

| Folder | Purpose |
| :--- | :--- |
| `.github/workflows` | CI/CD pipelines (Week 6) |
| `docs` | Proposal and architecture diagrams |
| `src/client` | Frontend application |
| `src/server` | Backend API and database logic |
| `ops/docker` | Dockerfiles and `docker-compose.yml` |
| `ops/observability` | Prometheus and Grafana configuration |
| `tests` | End-to-end test suites (Week 5) |

## How to Run

Not available yet — this repository currently contains no application code.
Local and Docker run instructions will be added here as the server and client are implemented (Weeks 3–6).

## AI Usage

AI assistance was used to draft this README and to scaffold the repository structure. All content was reviewed and edited by the author, who is responsible for its accuracy. A full AI reflection is part of the Week 7 final deliverable.

---
*This repository is for academic use. No secrets or API keys are committed; see `.gitignore`.*
