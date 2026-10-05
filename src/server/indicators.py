"""Indicators computed from a coverage's stored annual figures.

Pure arithmetic, no I/O: the LLM in insight.py only rewords what this module
returns, so a wrong number can be traced here and nowhere else. A value that
cannot be computed is None, never zero, so the summary can say "not available".
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Protocol

import edgar

# A prior year's figure must end about one year before the latest one. The same
# 350-day floor edgar_collection uses for "annual", plus room for 53-week years.
MIN_YEAR_GAP_DAYS = 350
MAX_YEAR_GAP_DAYS = 380

# Percentages are shown to one decimal place; more would be false precision.
PERCENT_STEP = Decimal("0.1")


class FinancialRow(Protocol):
    """The fields read from a CoverageFinancial row (a plain object works in tests)."""

    concept: str
    period_end: date
    value: Decimal
    accn: str
    form: str
    filed: date


@dataclass(frozen=True)
class Source:
    """One filing a computed indicator rests on."""

    concept: str
    accn: str
    form: str
    filed: date
    url: str


@dataclass(frozen=True)
class Indicators:
    """The latest fiscal year's indicators and the filings behind them."""

    period_end: date
    values: dict[str, float | None]
    sources: list[Source]


def filing_url(cik: str, accn: str) -> str:
    """The EDGAR folder for one filing, so a reader can open the source document."""
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/"


def _percent(numerator: Decimal | None, denominator: Decimal | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    # Rounded as Decimal: float rounding turns 1.15 into 1.1.
    percent = (numerator / denominator * 100).quantize(PERCENT_STEP, ROUND_HALF_UP)
    return float(percent)


def _growth(current: Decimal | None, previous: Decimal | None) -> float | None:
    if current is None or previous is None:
        return None
    return _percent(current - previous, previous)


def _one_revenue_series(rows: list[FinancialRow]) -> list[FinancialRow]:
    """Revenue rows of a single tag: the one reaching the latest period.

    Re-collection can leave both revenue tags stored; mixing them would compare
    two different definitions of revenue. Ties go to REVENUE_CONCEPTS order.
    """
    by_concept = {
        concept: [row for row in rows if row.concept == concept]
        for concept in edgar.REVENUE_CONCEPTS
    }
    present = [concept for concept in edgar.REVENUE_CONCEPTS if by_concept[concept]]
    if not present:
        return []
    chosen = max(
        present,
        key=lambda c: (
            max(row.period_end for row in by_concept[c]),
            -edgar.REVENUE_CONCEPTS.index(c),
        ),
    )
    return by_concept[chosen]


def compute_indicators(cik: str, rows: Iterable[FinancialRow]) -> Indicators | None:
    """Indicators for the latest fiscal year in ``rows``, or None if there are no rows.

    The latest year is the latest revenue period (or any period, if revenue was
    never reported). Every figure used must end on that date; the prior-year
    revenue must end 350-380 days earlier and come from the same revenue tag.
    """
    rows = list(rows)
    if not rows:
        return None

    revenue_rows = _one_revenue_series(rows)
    anchor = max(row.period_end for row in (revenue_rows or rows))

    def at_anchor(concepts: Iterable[str]) -> FinancialRow | None:
        wanted = set(concepts)
        return next(
            (row for row in rows if row.concept in wanted and row.period_end == anchor),
            None,
        )

    revenue = next((row for row in revenue_rows if row.period_end == anchor), None)
    net_income = at_anchor([edgar.NET_INCOME_CONCEPT])
    assets = at_anchor([edgar.ASSETS_CONCEPT])
    equity = at_anchor([edgar.EQUITY_CONCEPT])
    prior_revenue = next(
        (
            row
            for row in revenue_rows
            if MIN_YEAR_GAP_DAYS <= (anchor - row.period_end).days <= MAX_YEAR_GAP_DAYS
        ),
        None,
    )

    def value(row: FinancialRow | None) -> Decimal | None:
        return None if row is None else row.value

    values = {
        "revenue_growth_pct": _growth(value(revenue), value(prior_revenue)),
        "net_margin_pct": _percent(value(net_income), value(revenue)),
        "equity_ratio_pct": _percent(value(equity), value(assets)),
    }

    used = [row for row in (revenue, prior_revenue, net_income, assets, equity) if row]
    sources: list[Source] = []
    seen: set[tuple[str, str]] = set()
    for row in used:
        key = (row.concept, row.accn)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            Source(row.concept, row.accn, row.form, row.filed, filing_url(cik, row.accn))
        )

    return Indicators(period_end=anchor, values=values, sources=sources)
