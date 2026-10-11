from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from vps_tracker.config import Config, get_config, load_config, using_config
from vps_tracker.fx import Rates
from vps_tracker.providers import cloudcone, racknerd
from vps_tracker.rank import rank_plans, select_plans


def test_custom_sources_and_context_reset(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("""[providers.racknerd]
sources = ["https://www.racknerd.com/specials/", "https://www.racknerd.com/NewYear/"]
[ranking]
min_ram_gb = 2
sort_by = "cny_per_gb"
[alerts]
enabled = true
threshold_cny = "20"
""")
    config = load_config(path)
    assert config.min_ram_gb == 2
    assert config.sort_by == "cny_per_gb"
    assert config.alert_threshold_cny == 20
    assert config.alerts_enabled
    original = get_config()
    with using_config(config):
        assert get_config() is config
    assert get_config() == original


@pytest.mark.parametrize("failure", ["http", "parse"])
def test_source_fallback_on_http_error_or_changed_html(monkeypatch, html, failure):
    config = replace(
        Config(), sources={"racknerd": ("https://site.com/broken", "https://site.com/good")}
    )
    calls = []

    def get(url):
        calls.append(url)
        if url.endswith("broken"):
            if failure == "http":
                response = httpx.Response(404, request=httpx.Request("GET", url))
                response.raise_for_status()
            return httpx.Response(200, text="<h1>Ended campaign</h1>")
        return httpx.Response(200, text=html("racknerd.html"))

    monkeypatch.setattr(racknerd.requester, "get", get)
    with using_config(config):
        assert len(racknerd.fetch()) == 2
    assert calls == ["https://site.com/broken", "https://site.com/good"]


def test_all_sources_fail_with_each_reason(monkeypatch):
    config = replace(Config(), sources={"racknerd": ("https://site.com/a", "https://site.com/b")})
    monkeypatch.setattr(racknerd.requester, "get", lambda url: httpx.Response(200, text="bad"))
    with using_config(config), pytest.raises(RuntimeError, match="所有来源均失败") as error:
        racknerd.fetch()
    assert "https://site.com/a" in str(error.value) and "https://site.com/b" in str(error.value)


def test_cloudcone_terms_are_not_a_same_price_guarantee(monkeypatch, html):
    assert "无锁价保证" in cloudcone.parse_renewal_rules(html("cloudcone-terms.html"))
    assert cloudcone.parse_renewal_rules("<p>Renews for the same length</p>") is None
    monkeypatch.setattr(
        cloudcone.requester,
        "get",
        lambda url: httpx.Response(
            200,
            text=html("cloudcone-terms.html" if "terms" in url else "cloudcone-live.html"),
        ),
    )
    plans = cloudcone.fetch()
    assert all(p.renewal_same is None for p in plans)
    assert all("45天" in p.renewal_note and p.renewal_url.endswith("/terms/") for p in plans)


def test_failed_renewal_source_does_not_fail_provider(monkeypatch, html):
    def get(url):
        if "terms" in url:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, text=html("cloudcone-live.html"))

    monkeypatch.setattr(cloudcone.requester, "get", get)
    assert len(cloudcone.fetch()) == 6


def test_filters_and_per_gb_sort_keep_absolute_prices(plan):
    fx = Rates({"USD": Decimal(1), "CNY": Decimal(7)}, datetime.now(UTC))
    one = plan(ram_gb=1, price=Decimal(12), name="One")
    two = plan(ram_gb=2, price=Decimal(18), name="Two")
    four = plan(ram_gb=4, price=Decimal(24), name="Four")
    ranked = rank_plans([one, two, four], fx)
    selected = select_plans(ranked, 2, "cny_per_gb")
    assert [p.plan.name for p in selected] == ["Four", "Two"]
    assert selected[0].monthly_cny == 14
    assert selected[0].cny_per_gb == Decimal("3.5")


@pytest.mark.parametrize("minimum", [-1, float("nan"), float("inf")])
def test_invalid_filter_rejected(minimum):
    with pytest.raises(ValueError):
        select_plans([], minimum)
