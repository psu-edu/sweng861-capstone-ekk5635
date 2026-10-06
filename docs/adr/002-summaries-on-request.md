# ADR-002: Generate summaries on request and store them; defer the scheduled worker

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

The proposal planned a scheduled worker running from the same image as the API. Its reason was the course inference server's limit on calls per time window: a summary could not be generated inside a request, so a worker would generate summaries in the background and the API would only read them.

Building a worker means a second entrypoint, a schedule, a service identity that may write only to the coverage it was given, and its own failure reporting and tests. That did not fit the time left before the final package. Measured on the running stack, one generation took about 3 seconds against OpenAI `gpt-4o-mini`, well inside an HTTP request.

## Decision

- `POST /api/coverages/{id}/summary` computes the indicators, calls the LLM, and stores one summary row per coverage, replacing any earlier one.
- `GET /api/coverages/{id}/summary` only reads that row. Opening a page never calls the LLM, so it spends no quota.
- The user starts generation with a button. Nothing calls the LLM automatically.
- The scheduled worker is deferred to future work.

## Consequences

- No new process, schedule, or service identity; the feature is one router, one client module, and their tests.
- The user waits for the model during generation: the client's read timeout is 20 seconds, with one retry. The page shows a "Generating…" state and locks both actions meanwhile.
- The database transaction is closed before the LLM call so a slow model does not hold a connection.
- Summaries do not refresh by themselves when new filings appear; the user collects figures and regenerates.
- A future worker can call the same logic in `summaries.py`; the stored row and the read endpoint would not change.
