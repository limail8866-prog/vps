import json
from pathlib import Path

import httpx
import pytest

from vps_tracker.providers import buyvm, dedirock
from vps_tracker.providers.common import ParseError


def stock_script():
    return (Path(__file__).parent / "fixtures/buyvm-stock.js").read_text()


def test_dedirock_real_counter_prices_and_vps_only(html):
    plans = dedirock.parse(html("dedirock-live.html"))
    assert len(plans) == 12
    assert [str(p.price) for p in plans] == [
        "5.99",
        "8.99",
        "12.99",
        "5.99",
        "8.99",
        "12.99",
        "3.99",
        "5.99",
        "9.99",
        "34.99",
        "44.99",
        "54.99",
    ]
    assert plans[0].cpu == 1 and plans[0].ram_gb == 1 and plans[0].bandwidth_tb == 0.75
    assert plans[0].billing_cycle == "monthly"
    assert plans[-1].billing_cycle == "annually"
    assert all("/cart.php" not in p.url and "ryzen" not in p.url for p in plans)


def test_dedirock_missing_counter_value_does_not_use_zero_or_struck_price(html):
    page = html("dedirock-live.html").replace('data-to-value="', 'data-missing-value="')
    with pytest.raises(ParseError):
        dedirock.parse(page)


def test_buyvm_real_html_and_stock_exclude_disabled_locations(html):
    plans = buyvm.parse(html("buyvm-live.html"), stock_script())
    assert len(plans) == 17
    assert all(p.bandwidth_tb is None for p in plans)
    assert all(p.ram_gb >= 2 for p in plans)  # 512MB 和 1GB 本次全地区售罄
    assert all(p.billing_cycle == "monthly" for p in plans)
    assert {p.name for p in plans if p.ram_gb == 2} == {
        "SLICE 2048 — New York",
        "SLICE 2048 — Miami",
    }
    assert str(plans[0].price) == "7.00"
    assert all("Las Vegas" not in p.name for p in plans if p.ram_gb <= 16)


def test_buyvm_all_stock_disabled_is_a_clear_failure(html):
    stock = buyvm.parse_stock(stock_script())
    for locations in stock.values():
        for location in locations:
            location["disabled"] = "true"
    script = "var plans = " + json.dumps({"slice": stock})
    with pytest.raises(ParseError, match="暂无可售库存"):
        buyvm.parse(html("buyvm-live.html"), script)


def test_buyvm_unclear_inventory_is_not_guessed_available(html):
    stock = buyvm.parse_stock(stock_script())
    stock["512"][0]["disabled"] = "unknown"
    with pytest.raises(ParseError, match="状态不明确"):
        buyvm.parse(html("buyvm-live.html"), "var plans = " + json.dumps({"slice": stock}))


def test_buyvm_changed_stock_script_is_a_failure():
    with pytest.raises(ParseError):
        buyvm.parse_stock("console.log('changed');")


def test_buyvm_fetch_downloads_stock_script_with_shared_requester(monkeypatch, html):
    calls = []

    def get(url):
        calls.append(url)
        return httpx.Response(
            200, text=stock_script() if "plans.js" in url else html("buyvm-live.html")
        )

    monkeypatch.setattr(buyvm.requester, "get", get)
    assert len(buyvm.fetch()) == 17
    assert calls[0] == buyvm.SOURCE_URL
    assert "/assets/js/plans.js" in calls[1]


def test_dedirock_fetch_interface(monkeypatch, html):
    monkeypatch.setattr(
        dedirock.requester, "get", lambda url: httpx.Response(200, text=html("dedirock-live.html"))
    )
    assert len(dedirock.fetch()) == 12
