"""The LLM client, driven through httpx.MockTransport so no test touches the network.

Each test counts the requests the client made, because the retry policy is part
of the contract: a 429 must cost exactly one call, a 5xx at most two.
"""

import json

import httpx
import pytest

import insight
from config import DEFAULT_LLM_BASE_URL, get_settings

COMPANY = "Apple Inc."
INDICATORS = {"revenue_growth_pct": 2.0, "net_margin_pct": 24.3, "equity_ratio_pct": None}


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    # The retry waits a second; the tests check that it retries, not how long.
    monkeypatch.setattr(insight.time, "sleep", lambda seconds: None)


@pytest.fixture
def fresh_settings(monkeypatch):
    """Lets a test change an environment variable that get_settings() has cached."""

    def apply(**env: str) -> None:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()

    yield apply
    get_settings.cache_clear()


def _client(*responses):
    """A client that answers with the given responses in order and records each request."""
    calls: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def _completion(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_messages_carry_only_the_company_and_the_indicators():
    system, user = insight.build_messages(COMPANY, INDICATORS)

    assert system == {"role": "system", "content": insight.SYSTEM_PROMPT}
    assert user["role"] == "user"
    assert json.loads(user["content"]) == {"company": COMPANY, "indicators": INDICATORS}


def test_returns_the_trimmed_summary_and_sends_the_expected_request():
    client, calls = _client(_completion("  Revenue grew slightly.  "))

    summary = insight.request_summary(COMPANY, INDICATORS, client=client)

    assert summary == "Revenue grew slightly."
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "http://llm.example.invalid/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-llm-key"
    body = json.loads(request.content)
    assert body["model"] == "drift"
    assert "drift_debug" not in body
    assert body["temperature"] == 0
    assert body["max_tokens"] == insight.MAX_TOKENS
    assert body["messages"] == insight.build_messages(COMPANY, INDICATORS)


def test_without_a_key_no_request_is_made(fresh_settings):
    fresh_settings(LLM_API_KEY="")
    client, calls = _client()

    with pytest.raises(insight.InsightNotConfigured):
        insight.request_summary(COMPANY, INDICATORS, client=client)
    assert calls == []


def test_openai_settings_change_only_the_url_and_model(fresh_settings):
    fresh_settings(LLM_BASE_URL="https://api.openai.com", LLM_MODEL="gpt-4o-mini")
    client, calls = _client(_completion("Summary."))

    insight.request_summary(COMPANY, INDICATORS, client=client)

    assert str(calls[0].url) == "https://api.openai.com/v1/chat/completions"
    body = json.loads(calls[0].content)
    assert body["model"] == "gpt-4o-mini"
    assert "drift_debug" not in body


def test_the_drift_only_field_is_sent_to_the_course_server(fresh_settings):
    fresh_settings(LLM_BASE_URL=DEFAULT_LLM_BASE_URL)
    client, calls = _client(_completion("Summary."))

    insight.request_summary(COMPANY, INDICATORS, client=client)

    assert json.loads(calls[0].content)["drift_debug"] is False


def test_a_malformed_base_url_is_a_configuration_error(fresh_settings):
    fresh_settings(LLM_BASE_URL="http://llm:port")
    client, calls = _client()

    with pytest.raises(insight.InsightNotConfigured):
        insight.request_summary(COMPANY, INDICATORS, client=client)
    assert calls == []


def test_rate_limit_is_not_retried():
    client, calls = _client(httpx.Response(429))

    with pytest.raises(insight.InsightUnavailable):
        insight.request_summary(COMPANY, INDICATORS, client=client)
    assert len(calls) == 1


def test_rejected_key_is_reported_without_logging_the_key(caplog):
    client, calls = _client(httpx.Response(401))

    with pytest.raises(insight.InsightResponseError):
        insight.request_summary(COMPANY, INDICATORS, client=client)
    assert len(calls) == 1
    assert "test-llm-key" not in caplog.text


def test_a_server_error_is_retried_once_then_succeeds():
    client, calls = _client(httpx.Response(503), _completion("Margins held steady."))

    assert insight.request_summary(COMPANY, INDICATORS, client=client) == "Margins held steady."
    assert len(calls) == 2


def test_repeated_server_errors_end_as_unavailable():
    client, calls = _client(httpx.Response(502), httpx.Response(502))

    with pytest.raises(insight.InsightUnavailable):
        insight.request_summary(COMPANY, INDICATORS, client=client)
    assert len(calls) == insight.MAX_ATTEMPTS


def test_timeouts_end_as_unavailable_not_as_an_httpx_error():
    client, calls = _client(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"))

    with pytest.raises(insight.InsightUnavailable):
        insight.request_summary(COMPANY, INDICATORS, client=client)
    assert len(calls) == insight.MAX_ATTEMPTS


def test_an_unexpected_status_is_not_retried():
    client, calls = _client(httpx.Response(400))

    with pytest.raises(insight.InsightResponseError):
        insight.request_summary(COMPANY, INDICATORS, client=client)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, text="not json"),
        _completion("   "),
    ],
    ids=["missing-choices", "not-json", "empty-text"],
)
def test_a_malformed_reply_is_a_response_error(response):
    client, _ = _client(response)

    with pytest.raises(insight.InsightResponseError):
        insight.request_summary(COMPANY, INDICATORS, client=client)
