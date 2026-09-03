# CoverageDesk — Course Project Proposal

**Eungchan Kang (`ekk5635`)** · SWENG 861 – Software Construction · Deliverable I, Week 2

## 1. Project Category & Title

**Project V — Bring Your Own Domain**

**CoverageDesk.** Tell it which companies you follow, and it tells you what shape each one is
in — how the finances have moved, and how openly the company reports — in plain language, with
every statement traced back to the filing it came from.

## 2. Why This Application Is Needed

**The information is public; the ability to read it is not.** Everything a public company is
required to disclose is already free through the SEC's EDGAR system. It arrives, though, as
hundreds of pages of prose and raw XBRL facts — a format built for regulators and analysts, not
for the person who simply wants to know whether the company they invested in, or work for, is
holding up. So an ordinary person asking *"how is this company doing?"* ends up trusting whoever
summarized it for them: a video, a forum thread, a paywalled report. The data is not missing.
The reading of it is.

**A general chatbot is not the same answer.** Ask one about a company and it will produce a
fluent paragraph without telling you which filing it came from, or whether it opened one at all.
For a question where being confidently wrong has a real cost, an answer with no source is not an
answer. CoverageDesk is built the other way round: the numbers are computed from filed data by
ordinary, testable code, the language model only turns those numbers into sentences, and every
sentence carries the filing behind it.

**What the user gets.** For each company they follow, two readings a non-expert can act on:

- **Financial condition** — how revenue, operating margin, and leverage have moved, computed
  from the company's own XBRL filings.
- **Disclosure transparency** — whether the company files on time and how often it amends what
  it already filed. A company that reports late or restates often is telling you something
  before its numbers do.

**Users.** The primary user is an **ordinary individual with no finance training** who follows a
handful of companies — they invested in them, work at one, or are studying them — and wants a
straight answer about each. A second user is a **reviewer**: a mentor or more experienced
colleague who reads someone else's coverage and confirms the reading is sound. That role gives
the `REVIEWED` state its meaning, and it is why the system needs role-based access control rather
than simple per-user isolation.

## 3. Core Features

**Must-Have**
1. **Coverage CRUD** — the user creates, edits, and deletes a *coverage*: a company plus the
   reason and the conditions they are watching it for. A coverage moves through `WATCHING` →
   `ANALYZING` → `REVIEWED` → `ARCHIVED`, and every query is scoped by `owner_id`.
2. **Social login and protected API** — OAuth 2.0 / OIDC login, JWT-based sessions, and two
   roles (Analyst, Reviewer) enforced by middleware.
3. **Financial and transparency metrics** — retrieve `companyfacts` and the filing history for a
   coverage's company, then compute year-over-year growth, operating margin, and debt ratio
   alongside two disclosure signals: filing timeliness and amendment frequency. This is ordinary
   arithmetic in a pure module, not model output.
4. **Plain-language summary with sources** — send the computed metrics, and only those, to the
   course DRIFT inference server, and store the resulting short summary on the coverage with the
   filings it was derived from.

**Nice-to-Have**
1. **Retrieval over filing text** — chunk and embed disclosure text with `qwen3-embedding` to
   find comparable passages across filings.
2. **New-filing alerts** — detect that a watched company has filed something new and move the
   coverage back out of `REVIEWED`.

## 4. Architecture & Tech Stack

**Style: Modular Monolith.** One deployable backend, divided into modules with explicit
boundaries. Microservices were considered and rejected: this is a seven-week, single-developer
project, and the cost of running, deploying, and observing several services would consume the
time the course spends on testing, containerization, and observability. The boundaries below are
drawn so a module could be extracted later if that were justified.

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
              (companyfacts, filings)       (chat + embeddings)
```

| Module | Responsibility |
| :--- | :--- |
| `auth` | OIDC login, JWT issue/verify, role checks |
| `coverage` | Coverage CRUD, ownership scoping, status transitions |
| `edgar` | EDGAR client, financial ratios and disclosure signals (pure, unit-testable) |
| `insight` | DRIFT client, prompt assembly, summary and source caching |

**Four decisions that shape the design**

- **The model never computes a number.** Ratios and disclosure signals are calculated in
  `edgar`, a pure module with no network or model dependency; `insight` receives finished values
  and may only phrase them. Every figure stays reproducible and testable, and a wrong summary
  traces to either the arithmetic or the wording — never both.
- **Every conclusion keeps its source.** A stored summary records the filings and metric values
  it came from, so *where did this come from* is answered with a document, not a claim.
- **Ownership is enforced at the query layer, not the view layer.** Every read and write of a
  coverage is filtered by `owner_id`, so a user cannot reach another user's record by guessing an
  identifier. This is the OWASP API risk — broken object-level authorization — the course asks us
  to design against.
- **LLM calls never happen inside a request.** The provided inference server allows a limited
  number of calls per window, so generating a summary on every page load would fail under
  ordinary use. A background job produces them and caches them on the coverage; the API only reads.

**Tech stack.** Next.js (React) client · FastAPI (Python) server · PostgreSQL · OAuth 2.0/OIDC
with JWT · SEC EDGAR `companyfacts` and `submissions` · DRIFT inference server · Docker Compose
and GitHub Actions.

## 5. Repository

https://github.com/psu-edu/sweng861-capstone-ekk5635

---

*AI usage: an assistant was used to pressure-test the scope of this proposal and to draft
wording. The domain, the module boundaries, the separation between computed metrics and
generated text, and the decision to keep retrieval out of the Must-Have set are mine, and I
revised the draft accordingly.*
