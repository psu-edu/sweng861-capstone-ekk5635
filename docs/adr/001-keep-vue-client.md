# ADR-001: Keep the Vue 3 client instead of Next.js

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

The Week 2 proposal named Next.js (React) for the client. During Weeks 4–6 the weekly assignments built the same product's client in Vue 3 with Vite and TypeScript: login, coverage list, detail and form pages, a central API client, route guards, and a test suite with about 99% line coverage. That client was already containerized and checked in CI.

The final package was due about four days after the port started. The client is a signed-in single-page app: the session token is held in memory, and no page is useful to a search engine or to a visitor without an account. Server-side rendering, the main reason to choose Next.js, gives this app nothing.

## Decision

Port the existing Vue 3 client into `src/client` and build the new summary page on it. Do not rewrite the client in Next.js.

## Consequences

- The tested client, its CI job, and its image are reused unchanged; the remaining time goes to the summary feature, documentation, and the demo.
- The stack differs from the proposal. The README and this record state the change so the requirements, architecture, and implementation still line up.
- No server-side rendering. If public, indexable pages were ever needed, this decision would have to be revisited.
