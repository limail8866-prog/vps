import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from vps_tracker.fx import Rates, fetch_rates, validate_rates
from vps_tracker.rank import rank_plans


class StubHTTP:
    def __init__(self, payload=None, error=None):
        self.payload, self.error = payload, error

    def get(self, url):
        if self.error:
            raise self.error
        return httpx.Response(200, json=self.payload)


def test_live_rates_and_cache_fallback(tmp_path):
    cache = tmp_path / "cache.json"
    live = fetch_rates(
        cache,
        StubHTTP(
            {
                "result": "success",
                "base_code": "USD",
                "rates": {"USD": 1, "CNY": 7, "EUR": 0.9},
            }
        ),
    )
    assert not live.cached
    assert live.cny_per_unit("USD") == 7
    saved = json.loads(cache.read_text())
    assert saved["base"] == "USD"
    cached = fetch_rates(cache, StubHTTP(error=httpx.ConnectError("offline")))
    assert cached.cached
    assert cached.rates == live.rates
    assert cached.fetched_at == live.fetched_at
    assert "offline" in cached.warning


@pytest.mark.parametrize(
    "contents",
    [
        None,
        "broken",
        '{"base":"EUR"}',
        "{}",
        '{"base":"USD","rates":[],"fetched_at":"2026-01-01T00:00:00+00:00"}',
        '{"base":"USD","rates":{"USD":1,"CNY":7},"fetched_at":"2026-01-01"}',
    ],
)
def test_no_valid_cache_is_error(tmp_path, contents):
    cache = tmp_path / "cache.json"
    if contents is not None:
        cache.write_text(contents)
    with pytest.raises(RuntimeError, match="无有效缓存"):
        fetch_rates(cache, StubHTTP(error=httpx.ConnectError("offline")))


@pytest.mark.parametrize("cny", [0, -1, "NaN", "Infinity"])
def test_bad_live_rates_do_not_poison_cache(tmp_path, cny):
    cache = tmp_path / "cache.json"
    fetch_rates(
        cache, StubHTTP({"result": "success", "base_code": "USD", "rates": {"USD": 1, "CNY": 7}})
    )
    before = cache.read_text()
    fallback = fetch_rates(
        cache, StubHTTP({"result": "success", "base_code": "USD", "rates": {"USD": 1, "CNY": cny}})
    )
    assert fallback.cached
    assert cache.read_text() == before


def test_wrong_base_rejected(tmp_path):
    with pytest.raises(RuntimeError):
        fetch_rates(
            tmp_path / "cache.json",
            StubHTTP(
                {
                    "result": "success",
                    "base_code": "EUR",
                    "rates": {"USD": 1, "CNY": 7},
                }
            ),
        )
    with pytest.raises(ValueError):
        validate_rates({"USD": 2, "CNY": 7})


def test_ranking_uses_exact_months_and_cross_currency(plan):
    rates = Rates({"USD": Decimal(1), "CNY": Decimal(7), "EUR": Decimal("0.5")}, datetime.now(UTC))
    annual = plan(price=Decimal("12"))
    monthly = plan(price=Decimal("2"), billing_cycle="monthly", renewal_same=False)
    euro = plan(price=Decimal("6"), currency="EUR")
    ranked = rank_plans([monthly, annual, euro], rates)
    assert [row.monthly_cny for row in ranked] == [Decimal(7), Decimal(7), Decimal(14)]
    assert ranked[-1].plan.renewal_same is False


@pytest.mark.parametrize(
    ("cycle", "months"),
    [
        ("monthly", 1),
        ("quarterly", 3),
        ("semiannually", 6),
        ("annually", 12),
        ("biennially", 24),
        ("triennially", 36),
    ],
)
def test_all_billing_cycles(plan, cycle, months):
    rates = Rates({"USD": Decimal(1), "CNY": Decimal(7)}, datetime.now(UTC))
    p = plan(price=Decimal(months), billing_cycle=cycle)
    assert rank_plans([p], rates)[0].monthly_cny == 7


@pytest.mark.parametrize("price", [Decimal(0), Decimal(-1), Decimal("NaN")])
def test_invalid_plan_prices(plan, price):
    with pytest.raises(ValueError):
        plan(price=price)
