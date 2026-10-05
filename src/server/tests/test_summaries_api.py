"""The summary endpoints, against the test database with the LLM replaced.

The fake records every call, so each test can also assert when the LLM must
not be reached at all: a stranger, a coverage with no figures, a plain read.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

import edgar
import insight
from conftest import needs_db

FY2025 = date(2025, 12, 31)
FY2024 = date(2024, 12, 31)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def financials(db_session, coverage):
    """Two years of revenue and one year of the other figures, all for Tesla."""
    from models import CoverageFinancial

    def row(concept, period_end, value, accn="0001628280-26-003952"):
        return CoverageFinancial(
            coverage_id=coverage.id, concept=concept, period_end=period_end,
            value=Decimal(value), unit="USD", form="10-K", accn=accn,
            filed=date(2026, 1, 29), source="sec_edgar",
        )

    db_session.add_all([
        row(edgar.REVENUE_CONCEPTS[0], FY2025, "400"),
        row(edgar.REVENUE_CONCEPTS[0], FY2024, "320", accn="0001628280-25-003063"),
        row(edgar.NET_INCOME_CONCEPT, FY2025, "100"),
        row(edgar.ASSETS_CONCEPT, FY2025, "1000"),
        row(edgar.EQUITY_CONCEPT, FY2025, "250"),
    ])
    db_session.commit()


class FakeLLM:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.reply: str | Exception = "Revenue grew by a quarter."

    def __call__(self, company, indicators, **kwargs):
        self.calls.append((company, indicators))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def llm(monkeypatch, db_session):
    fake = FakeLLM()
    fake.in_transaction: list[bool] = []
    original_call = fake.__call__

    def call(company, indicators, **kwargs):
        fake.in_transaction.append(db_session.in_transaction())
        return original_call(company, indicators, **kwargs)

    monkeypatch.setattr(insight, "request_summary", call)
    return fake


def _stored_count(db_session) -> int:
    from models import CoverageSummary

    return db_session.scalar(select(func.count()).select_from(CoverageSummary))


@needs_db
def test_generating_requires_a_token(api, coverage, llm):
    response = api.post(f"/api/coverages/{coverage.id}/summary")

    assert response.status_code == 401
    assert llm.calls == []


@needs_db
def test_generate_then_read_back(api, coverage, financials, owner_token, llm):
    url = f"/api/coverages/{coverage.id}/summary"

    created = api.post(url, headers=auth(owner_token))
    read = api.get(url, headers=auth(owner_token))

    assert created.status_code == 200
    body = created.json()
    assert body["summary"] == "Revenue grew by a quarter."
    assert body["model"] == "drift"
    assert body["period_end"] == "2025-12-31"
    assert body["indicators"] == {
        "fiscal_year_end": "2025-12-31",
        "revenue_growth_pct": 25.0,
        "net_margin_pct": 25.0,
        "equity_ratio_pct": 25.0,
    }
    assert {s["accn"] for s in body["sources"]} == {
        "0001628280-26-003952", "0001628280-25-003063",
    }
    assert all(s["url"].startswith("https://www.sec.gov/Archives/edgar/data/1318605/")
               for s in body["sources"])
    assert read.status_code == 200
    assert read.json() == body


@needs_db
def test_only_the_ticker_and_indicators_reach_the_llm(
    api, coverage, financials, owner_token, llm
):
    api.post(f"/api/coverages/{coverage.id}/summary", headers=auth(owner_token))

    company, indicators = llm.calls[0]
    assert company == "TSLA"
    assert coverage.title not in repr(llm.calls)
    assert set(indicators) == {
        "fiscal_year_end", "revenue_growth_pct", "net_margin_pct", "equity_ratio_pct",
    }


@needs_db
def test_regenerating_replaces_the_stored_summary(
    api, db_session, coverage, financials, owner_token, llm
):
    url = f"/api/coverages/{coverage.id}/summary"
    api.post(url, headers=auth(owner_token))
    llm.reply = "A second wording."

    api.post(url, headers=auth(owner_token))

    assert _stored_count(db_session) == 1
    assert api.get(url, headers=auth(owner_token)).json()["summary"] == "A second wording."


@needs_db
def test_reading_never_calls_the_llm(api, coverage, financials, owner_token, llm):
    url = f"/api/coverages/{coverage.id}/summary"
    api.post(url, headers=auth(owner_token))
    llm.calls.clear()

    api.get(url, headers=auth(owner_token))

    assert llm.calls == []


@needs_db
def test_reading_before_generating_is_404(api, coverage, owner_token, llm):
    response = api.get(f"/api/coverages/{coverage.id}/summary", headers=auth(owner_token))

    assert response.status_code == 404


@needs_db
@pytest.mark.parametrize("verb", ["post", "get"])
def test_another_users_coverage_is_404_and_costs_no_call(
    api, coverage, financials, other_token, llm, verb
):
    response = getattr(api, verb)(
        f"/api/coverages/{coverage.id}/summary", headers=auth(other_token)
    )

    assert response.status_code == 404
    assert llm.calls == []


@needs_db
def test_no_collected_figures_is_409_and_costs_no_call(
    api, db_session, coverage, owner_token, llm
):
    response = api.post(f"/api/coverages/{coverage.id}/summary", headers=auth(owner_token))

    assert response.status_code == 409
    assert llm.calls == []
    assert _stored_count(db_session) == 0


@needs_db
@pytest.mark.parametrize(
    "error, status, retry_after",
    [
        (insight.InsightNotConfigured("no key"), 503, None),
        (insight.InsightUnavailable("rate limit"), 503, "60"),
        (insight.InsightResponseError("bad body"), 502, None),
    ],
    ids=["not-configured", "unavailable", "bad-reply"],
)
def test_llm_failures_map_to_status_codes_and_store_nothing(
    api, db_session, coverage, financials, owner_token, llm, error, status, retry_after
):
    llm.reply = error

    response = api.post(f"/api/coverages/{coverage.id}/summary", headers=auth(owner_token))

    assert response.status_code == status
    assert response.headers.get("Retry-After") == retry_after
    text = response.text.lower()
    assert "openai" not in text and "drift" not in text and "httpx" not in text
    assert _stored_count(db_session) == 0


@needs_db
def test_no_database_transaction_is_held_open_during_the_llm_call(
    api, coverage, financials, owner_token, llm
):
    api.post(f"/api/coverages/{coverage.id}/summary", headers=auth(owner_token))

    assert llm.in_transaction == [False]


@needs_db
def test_a_failed_regeneration_keeps_the_previous_summary(
    api, coverage, financials, owner_token, llm
):
    url = f"/api/coverages/{coverage.id}/summary"
    api.post(url, headers=auth(owner_token))
    llm.reply = insight.InsightUnavailable("rate limit")

    failed = api.post(url, headers=auth(owner_token))

    assert failed.status_code == 503
    assert api.get(url, headers=auth(owner_token)).json()["summary"] == "Revenue grew by a quarter."


@needs_db
def test_without_a_ticker_the_cik_is_sent_instead(
    api, db_session, coverage, financials, owner_token, llm
):
    coverage.ticker = None
    db_session.commit()

    api.post(f"/api/coverages/{coverage.id}/summary", headers=auth(owner_token))

    assert llm.calls[0][0] == "CIK 0001318605"


@needs_db
def test_deleting_the_coverage_deletes_its_summary(
    api, db_session, coverage, financials, owner_token, llm
):
    api.post(f"/api/coverages/{coverage.id}/summary", headers=auth(owner_token))

    deleted = api.delete(f"/api/coverages/{coverage.id}", headers=auth(owner_token))

    assert deleted.status_code == 204
    assert _stored_count(db_session) == 0
