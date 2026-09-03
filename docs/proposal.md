# CoverageDesk — Course Project Proposal

**Eungchan Kang (`ekk5635`)** · SWENG 861 – Software Construction · Deliverable I, Week 2

## 1. Project Category & Title

**Project V — Bring Your Own Domain** (approved by the instructor, 2026-09-01).
**CoverageDesk**: track the companies you follow; the app reads their SEC filings for you.

## 2. Problem & Users

**Problem.** Everything a public company is required to disclose is already free and public
through the SEC's EDGAR system, but it arrives in a form almost nobody can use: a single annual
report runs hundreds of pages, and the financial data behind it is published as raw XBRL facts.
Someone who follows even a handful of companies therefore faces a recurring manual task — pull
the numbers, compute how they moved, read the new disclosures, and decide whether anything
changed that matters *to them specifically*. The information is not missing; the work of turning
it into an answer is what is missing.

**Users.** The primary user is an **individual investor or finance student** who deliberately
follows a small set of companies (roughly five to twenty) and cares about fundamentals rather
than price movement. They already know *why* they are watching each company; what they lack is a
place to record that reasoning and have it kept up to date.

A second user is a **reviewer** — a study-group lead, mentor, or senior analyst who reads other
people's coverage and confirms when an analysis is sound. This role is what gives the `REVIEWED`
state its meaning, and it is why the system needs role-based access control rather than simple
per-user isolation.

## 3. Core Features

**Must-Have**
1. **Coverage CRUD** — the user creates, edits, and deletes a *coverage*: a company plus the
   reason and conditions they are tracking it for. A coverage moves through `DRAFT` →
   `ACTIVE` → `REVIEWED`, and every query is scoped by `owner_id`.
2. **Social login and protected API** — OAuth 2.0 / OIDC login, JWT-based sessions, and two
   roles (Analyst, Reviewer) enforced by middleware.
3. **EDGAR integration and financial metrics** — retrieve `companyfacts` for a coverage's
   company and compute year-over-year growth, operating margin, and debt ratio.
4. **LLM-generated summary** — send the computed metrics to the course DRIFT inference server
   and store a short written summary on the coverage.

**Nice-to-Have**
1. **Retrieval over filing text** — chunk and embed disclosure text with `qwen3-embedding` to
   find comparable passages across filings.
2. **New-filing alerts** — detect that a tracked company has filed something new and move the
   coverage back into an unreviewed state.

## 4. Architecture & Tech Stack

**Style: Modular Monolith.** One deployable backend, divided into modules with explicit
boundaries. Microservices were considered and rejected: this is a seven-week, single-developer
project, and the operational cost of running, deploying, and observing several services would
consume time that the course spends on testing, containerization, and observability instead.
The module boundaries below are drawn so that a service could be extracted later if it were
ever justified.

```
  Browser
     │
     ▼
  Next.js client  ──HTTPS──►  FastAPI server ──────►  PostgreSQL
                                   │                  (users, coverages,
                                   │                   cached metrics & summaries)
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              SEC EDGAR API                 DRIFT LLM server
              (companyfacts, XBRL)          (chat + embeddings)
```

**Server modules**

| Module | Responsibility |
| :--- | :--- |
| `auth` | OIDC login, JWT issue/verify, role checks |
| `coverage` | Coverage CRUD, ownership scoping, status transitions |
| `edgar` | EDGAR client and financial-metric computation (pure, unit-testable) |
| `insight` | DRIFT client, prompt assembly, summary caching |

**Three decisions that shape the design**

- **Ownership is enforced at the query layer, not the view layer.** Every read and write of a
  coverage is filtered by `owner_id`, so a user cannot reach another user's record by guessing
  an identifier. This is the OWASP API risk (broken object-level authorization) the course
  asks us to design against.
- **LLM calls are never made inside a request.** The provided inference server allows a limited
  number of calls per window, so generating a summary on every page load would fail under
  ordinary use. Summaries are produced by a background job and cached on the coverage record;
  the API only ever reads them.
- **EDGAR data is read-only.** Filings and financial facts are fetched and cached, never edited
  by users. This is why the user-owned entity is the *coverage* — the tracking decision — rather
  than the financial data itself, which the user does not author.

**Tech stack.** Next.js (React) client · FastAPI (Python) server · PostgreSQL · OAuth 2.0/OIDC
with JWT · SEC EDGAR `companyfacts` · DRIFT inference server · Docker Compose and GitHub Actions.

## 5. Repository

https://github.com/psu-edu/sweng861-capstone-ekk5635

---

*AI usage: an assistant was used to pressure-test the scope of this proposal and to draft
wording. The domain, the module boundaries, and the decision to keep retrieval out of the
Must-Have set are mine, and I revised the draft accordingly.*
