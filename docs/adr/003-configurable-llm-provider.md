# ADR-003: Make the LLM provider configurable; use OpenAI while DRIFT is unreachable

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

The proposal used the course DRIFT inference server for plain-language summaries. On 2026-10-05, while the LLM client was being built, the DRIFT server refused connections. The feature could not be developed or demonstrated against it.

DRIFT and OpenAI both accept the OpenAI-compatible chat completions request (`POST /v1/chat/completions`), so one client can talk to either.

## Decision

- `insight.py` speaks only the OpenAI-compatible chat API. The endpoint, model, and key come from `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` in `.env`.
- The defaults point at DRIFT (`LLM_MODEL=drift`), so restoring the course server needs only its key.
- The local and demo environment uses OpenAI `gpt-4o-mini`.
- With no key set, the summary endpoint answers 503 and the rest of the service runs normally.

## Consequences

- Switching providers is a configuration change, not a code change.
- Data goes to a third-party service. Only the ticker or CIK and the computed indicators are sent, never a user's title or notes; `temperature` is 0 and replies are capped at 300 tokens.
- OpenAI calls cost money and need a personal key, kept only in the git-ignored `.env`.
- Each stored summary records the model that wrote it, so summaries from different providers can be told apart.
