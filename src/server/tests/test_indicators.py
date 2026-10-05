"""Indicator arithmetic, on plain rows: no database and no network."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import edgar
from indicators import compute_indicators, filing_url

CIK = "0000320193"
FY2025 = date(2025, 9, 27)
FY2024 = date(2024, 9, 28)
REVENUE = edgar.REVENUE_CONCEPTS[0]


@dataclass
class Row:
    concept: str
    period_end: date
    value: Decimal
    accn: str = "0000320193-25-000079"
    form: str = "10-K"
    filed: date = date(2025, 10, 31)


def _full_year(**overrides):
    values = {
        "revenue": Decimal("400"),
        "prior_revenue": Decimal("320"),
        "net_income": Decimal("100"),
        "assets": Decimal("1000"),
        "equity": Decimal("250"),
    }
    values.update(overrides)
    return [
        Row(REVENUE, FY2025, values["revenue"]),
        Row(REVENUE, FY2024, values["prior_revenue"], accn="0000320193-24-000123"),
        Row(edgar.NET_INCOME_CONCEPT, FY2025, values["net_income"]),
        Row(edgar.ASSETS_CONCEPT, FY2025, values["assets"]),
        Row(edgar.EQUITY_CONCEPT, FY2025, values["equity"]),
    ]


def test_no_rows_gives_none():
    assert compute_indicators(CIK, []) is None


def test_computes_growth_margin_and_equity_ratio_for_the_latest_year():
    result = compute_indicators(CIK, _full_year())

    assert result.period_end == FY2025
    assert result.values == {
        "revenue_growth_pct": 25.0,
        "net_margin_pct": 25.0,
        "equity_ratio_pct": 25.0,
    }


def test_percentages_are_rounded_to_one_decimal():
    result = compute_indicators(CIK, _full_year(net_income=Decimal("1"), revenue=Decimal("3")))

    assert result.values["net_margin_pct"] == 33.3


def test_a_loss_gives_a_negative_margin():
    result = compute_indicators(CIK, _full_year(net_income=Decimal("-40")))

    assert result.values["net_margin_pct"] == -10.0


def test_missing_figures_are_none_not_zero():
    rows = [Row(REVENUE, FY2025, Decimal("400"))]

    result = compute_indicators(CIK, rows)

    assert result.values == {
        "revenue_growth_pct": None,
        "net_margin_pct": None,
        "equity_ratio_pct": None,
    }


def test_a_zero_denominator_is_none():
    result = compute_indicators(CIK, _full_year(prior_revenue=Decimal("0"), assets=Decimal("0")))

    assert result.values["revenue_growth_pct"] is None
    assert result.values["equity_ratio_pct"] is None


def test_prior_revenue_must_be_about_one_year_earlier():
    rows = _full_year()
    rows[1] = Row(REVENUE, date(2023, 9, 30), Decimal("320"))

    result = compute_indicators(CIK, rows)

    assert result.values["revenue_growth_pct"] is None


def test_figures_from_another_year_are_not_mixed_in():
    rows = [r for r in _full_year() if r.concept != edgar.NET_INCOME_CONCEPT]
    rows.append(Row(edgar.NET_INCOME_CONCEPT, FY2024, Decimal("90")))

    result = compute_indicators(CIK, rows)

    assert result.values["net_margin_pct"] is None


def test_without_revenue_the_latest_period_is_used():
    rows = [
        Row(edgar.ASSETS_CONCEPT, FY2025, Decimal("1000")),
        Row(edgar.EQUITY_CONCEPT, FY2025, Decimal("250")),
        Row(edgar.ASSETS_CONCEPT, FY2024, Decimal("900")),
    ]

    result = compute_indicators(CIK, rows)

    assert result.period_end == FY2025
    assert result.values["equity_ratio_pct"] == 25.0
    assert result.values["net_margin_pct"] is None


def test_sources_list_each_filing_used_once_with_its_edgar_url():
    result = compute_indicators(CIK, _full_year())

    pairs = [(s.concept, s.accn) for s in result.sources]
    assert len(pairs) == len(set(pairs)) == 5
    prior = next(s for s in result.sources if s.accn == "0000320193-24-000123")
    assert prior.url == "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/"


def test_filing_url_drops_leading_zeros_and_dashes():
    assert filing_url("0000320193", "0000320193-25-000079") == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/"
    )


def test_one_filing_reporting_both_revenue_years_is_listed_once():
    # The latest 10-K restates the prior year, so both revenue rows often share it.
    rows = _full_year()
    rows[1] = Row(REVENUE, FY2024, Decimal("320"))

    result = compute_indicators(CIK, rows)

    assert [s.accn for s in result.sources if s.concept == REVENUE] == ["0000320193-25-000079"]
    assert result.values["revenue_growth_pct"] == 25.0


def test_percentages_round_half_up_in_decimal():
    # 23 / 2000 = 1.15%; float rounding would give 1.1.
    result = compute_indicators(CIK, _full_year(net_income=Decimal("23"), revenue=Decimal("2000")))

    assert result.values["net_margin_pct"] == 1.2


def test_two_stored_revenue_tags_are_never_mixed_whatever_the_row_order():
    older_tag = edgar.REVENUE_CONCEPTS[1]
    rows = _full_year() + [Row(older_tag, FY2024, Decimal("999"), accn="old")]

    forward = compute_indicators(CIK, rows)
    backward = compute_indicators(CIK, rows[::-1])

    assert forward.values["revenue_growth_pct"] == backward.values["revenue_growth_pct"] == 25.0
    assert "old" not in {s.accn for s in forward.sources}
