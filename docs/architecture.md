# Architecture

How CoverageDesk is built, from the system boundary down to the request flows. GitHub renders the diagrams below. Decisions that shaped them are in [`adr/`](adr/).

## 1. Context

Two kinds of users and three external systems. Only public data leaves the service: the LLM receives a ticker or CIK and computed indicators, never a user's own title or notes.

```mermaid
flowchart LR
  user(["User<br/>tracks the companies they cover"]):::person
  admin(["Admin<br/>audits every coverage"]):::person
  subgraph boundary["CoverageDesk"]
    system["SPA + API + database"]:::system
  end
  google["Google Identity<br/>OpenID Connect"]:::ext
  edgar["SEC EDGAR<br/>XBRL companyconcept API"]:::ext
  llm["LLM<br/>OpenAI-compatible chat API"]:::ext
  user -- "browser" --> system
  admin -- "same login, admin role" --> system
  system -- "login: code exchange + PKCE" --> google
  system -- "reported financials (JSON)" --> edgar
  system -- "indicators in, plain-language summary out" --> llm
  classDef person fill:#6b4c9a,stroke:#4a3470,color:#fff
  classDef system fill:#2f5d8a,stroke:#1f3a5f,color:#fff
  classDef ext fill:#8b949e,stroke:#57606a,color:#fff
```

## 2. Containers

Everything below runs from `ops/docker/docker-compose.yml`. The gateway is the only port for app traffic. Prometheus and Grafana bind to `127.0.0.1`; PostgreSQL is published on 5432 for local tools and the test database.

```mermaid
flowchart TB
  person(["User / Admin"]):::person
  subgraph browser["Browser"]
    spa["Single-page app<br/>Vue 3 + TypeScript<br/>session token in memory"]:::system
  end
  subgraph compose["Docker Compose project: coveragedesk"]
    gateway["Gateway<br/>nginx · :8000 → 80"]:::system
    web["Frontend<br/>nginx-unprivileged · uid 101<br/>serves the built SPA"]:::system
    api["API<br/>FastAPI on uvicorn<br/>JSON logs · /metrics"]:::system
    migrate["Migration job<br/>alembic upgrade head · runs once"]:::system
    db[("PostgreSQL 17<br/>users · coverages ·<br/>coverage_financials · coverage_summaries")]:::store
    prom["Prometheus<br/>127.0.0.1:9090<br/>SLO alert rules"]:::system
    graf["Grafana<br/>127.0.0.1:3000<br/>provisioned dashboard"]:::system
  end
  google["Google Identity"]:::ext
  edgar["SEC EDGAR"]:::ext
  llm["LLM API"]:::ext
  person --> spa
  spa -- "/, /api, /auth on :8000" --> gateway
  gateway -- "/api, /auth, /health, /docs, /openapi.json" --> api
  gateway -- "every other path" --> web
  api -- "SQLAlchemy / psycopg" --> db
  migrate -- "DDL, before the API starts" --> db
  prom -- "scrapes /metrics" --> api
  graf -- "PromQL" --> prom
  api -- "code exchange, JWKS" --> google
  api -- "companyconcept, retries" --> edgar
  api -- "chat completion, timeout + 1 retry" --> llm
  classDef person fill:#6b4c9a,stroke:#4a3470,color:#fff
  classDef system fill:#2f5d8a,stroke:#1f3a5f,color:#fff
  classDef store fill:#b26a00,stroke:#7a4a00,color:#fff
  classDef ext fill:#8b949e,stroke:#57606a,color:#fff
```

### API modules (`src/server`)

| Module | Responsibility |
| :--- | :--- |
| `main.py`, `oidc.py`, `tokens.py` | Google login (code flow + PKCE) and the service's own session JWT |
| `security.py` | Bearer token check on every protected route; admin role check |
| `coverages.py` | Coverage CRUD, filtered by `owner_id` |
| `financials.py`, `edgar.py`, `edgar_collection.py` | Collect figures from EDGAR and store them per period |
| `indicators.py` | Pure computation: revenue growth, net margin, equity ratio, and their source filings |
| `insight.py` | LLM client: sends indicators, returns text, maps failures to typed errors |
| `summaries.py` | Generate, store, and read a coverage's summary |
| `admin.py` | Read-only list of all coverages for admins |
| `errors.py` | One JSON error shape for every failure, including upstream ones |
| `health.py`, `metrics.py`, `request_logging.py` | Health probes, Prometheus metrics, request ID and JSON logs |

## 3. Data model

Every coverage belongs to one user, and every query filters by that owner. A coverage has at most one stored summary.

```mermaid
classDiagram
  class User {
    +int id
    +str google_sub unique
    +str email
    +str role user or admin
  }
  class Coverage {
    +int id
    +int owner_id FK
    +str title
    +str description
    +CoverageStatus status
    +str ticker
    +str cik immutable
  }
  class CoverageFinancial {
    +int coverage_id FK
    +str concept
    +date period_end
    +Decimal value
    +str form
    +str accn
    +date filed
  }
  class CoverageSummary {
    +int coverage_id FK unique
    +date period_end
    +json indicators
    +text summary
    +str model
    +json sources
    +datetime generated_at
  }
  class CoverageStatus {
    <<enumeration>>
    draft
    active
    archived
  }
  User "1" --> "*" Coverage : owns
  Coverage "1" --> "*" CoverageFinancial : has
  Coverage "1" --> "0..1" CoverageSummary : has
  Coverage --> CoverageStatus
```

`UNIQUE (owner_id, cik)`: one coverage per company per user; a duplicate answers 409.

## 4. Runtime flows

### 4.1 Collect financials

```mermaid
sequenceDiagram
  autonumber
  participant C as SPA
  participant A as API (financials)
  participant S as SEC EDGAR
  participant D as PostgreSQL
  C->>A: POST /api/coverages/{id}/financials
  A->>D: own coverage? (owner_id filter), else 404
  loop revenue, net income, assets, equity
    A->>S: GET companyconcept/CIK/us-gaap/Concept.json
    alt 200
      S-->>A: facts
      A->>D: upsert annual 10-K figures by period
    else 404 (concept not reported)
      S-->>A: skip this concept
    else 429, 5xx, or timeout after retries
      A-->>C: 503 + Retry-After
    else unusable response
      A-->>C: 502
    end
  end
  A-->>C: 200 {coverage_id, collected, concepts}
```

### 4.2 Generate a summary

The LLM is called only on POST; reading the summary is a plain database read. The database transaction is closed before the LLM call so a slow model does not hold a connection.

```mermaid
sequenceDiagram
  autonumber
  participant C as SPA
  participant A as API (summaries)
  participant D as PostgreSQL
  participant L as LLM API
  C->>A: POST /api/coverages/{id}/summary
  A->>D: own coverage? (owner_id filter), else 404
  A->>D: read stored figures
  alt no figures yet
    A-->>C: 409 collect first
  else figures present
    A->>A: compute indicators and source filings
    A->>D: end read transaction
    A->>L: ticker or CIK + indicators only
    alt text returned
      L-->>A: summary
      A->>D: upsert one row per coverage
      A-->>C: 200 summary, indicators, sources
    else no key, rate limited (429), or unreachable after retry
      A-->>C: 503
    else unusable response
      A-->>C: 502
    end
  end
```

## 5. Quality measures

| Concern | How it is handled | Checked by |
| :--- | :--- | :--- |
| Multi-tenancy | `owner_id` from the token in every query; another user's row is a 404 | pytest (`test_coverages_api.py`, `test_summaries_api.py`) |
| Untrusted model output | Rendered as text, never as HTML; only `https://www.sec.gov/` links | Vitest (`CoverageSummary.spec.ts`) |
| Secrets | `.env` only; CI fails if a `.env` file is tracked; Trivy secret scan on images | CI `audit`, `package` |
| Dependencies and images | pip-audit, npm audit, Trivy on both images | CI `audit`, `package` |
| Availability | Health and readiness probes; SLO alerts on login success, API errors, and latency | CI `alert-rules` (promtool) |
| Code quality | ruff, ESLint and oxlint, 80% coverage gates on server and client | CI `backend`, `frontend` |
