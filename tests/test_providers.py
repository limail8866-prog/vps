from decimal import Decimal

import pytest

from vps_tracker.providers import cloudcone, racknerd
from vps_tracker.providers.common import ParseError, parse_cards, renewal_policy


def test_racknerd_snapshot(html):
    plans = racknerd.parse(html("racknerd.html"))
    assert len(plans) == 2
    assert plans[0].provider == "RackNerd"
    assert plans[0].price == Decimal("10.99")
    assert plans[0].billing_cycle == "annually"
    assert plans[0].renewal_same is True
    assert (plans[0].cpu, plans[0].ram_gb, plans[0].disk_gb, plans[0].bandwidth_tb) == (1, 1, 20, 2)
    assert plans[1].price == Decimal("18.99")
    assert plans[1].renewal_same is None
    assert plans[1].cpu == 2
    assert plans[1].ram_gb == 2
    assert plans[1].disk_gb == 40
    assert plans[0].fetched_at.tzinfo is not None
    assert "&pid=101" in plans[0].url


def test_cloudcone_snapshot(html):
    plans = cloudcone.parse(html("cloudcone.html"))
    assert len(plans) == 2
    assert plans[0].price == Decimal("16.99")
    assert plans[0].renewal_same is False
    assert plans[1].billing_cycle == "monthly"
    assert plans[1].renewal_same is True
    assert (plans[1].cpu, plans[1].ram_gb, plans[1].disk_gb, plans[1].bandwidth_tb) == (2, 2, 50, 4)


def test_racknerd_actual_page_snapshot(html):
    plans = racknerd.parse(html("racknerd-live.html"))
    assert len(plans) == 5
    assert [p.price for p in plans] == list(
        map(Decimal, ["21.99", "35.99", "59.99", "89.99", "119.99"])
    )
    assert all(p.billing_cycle == "annually" and p.renewal_same is True for p in plans)
    assert [(p.cpu, p.ram_gb, p.disk_gb, p.bandwidth_tb) for p in plans] == [
        (1, 1, 20, 3),
        (2, 2, 35, 5),
        (3, 4, 60, 7),
        (6, 6, 100, 12),
        (7, 8, 150, 20),
    ]


def test_cloudcone_actual_page_uses_billed_annual_prices(html):
    plans = cloudcone.parse(html("cloudcone-live.html"))
    assert len(plans) == 6
    assert [p.price for p in plans] == list(map(Decimal, [28, 46, 69, 92, 174, 322]))
    assert all(p.billing_cycle == "annually" and p.renewal_same is None for p in plans)
    assert [(p.cpu, p.ram_gb, p.disk_gb, p.bandwidth_tb) for p in plans] == [
        (2, 1, 30, 4),
        (4, 2, 60, 7),
        (6, 3, 90, 8.5),
        (8, 4, 120, 10),
        (12, 8, 240, 15),
        (14, 16, 480, 25),
    ]


def test_cannot_fall_back_to_advertised_monthly_price_when_billed_cycle_unknown(html):
    page = html("cloudcone-live.html").replace("per year", "per term")
    with pytest.raises(ParseError):
        cloudcone.parse(page)


def test_racknerd_renewal_question_alone_does_not_imply_same_price(html):
    page = html("racknerd-live.html")
    page = page.replace(
        "Yes. These RackNerd VPS specials are lifetime recurring. "
        "You can renew at the same rate for as long as you decide to keep the service.",
        "Contact support for renewal information.",
    )
    assert all(p.renewal_same is None for p in racknerd.parse(page))


@pytest.mark.parametrize("snapshot", ["changed.html"])
def test_does_not_join_unrelated_specs_and_price(html, snapshot):
    with pytest.raises(ParseError, match="未解析出"):
        racknerd.parse(html(snapshot))


@pytest.mark.parametrize("page", ["", "<h1>CAPTCHA</h1>", "<h1>Sold out</h1>"])
def test_empty_or_changed_page_is_failure(page):
    with pytest.raises(ParseError):
        cloudcone.parse(page)


def test_duplicate_links_are_deduplicated(html):
    page = html("racknerd.html")
    page = page.replace(
        "Order now</a>",
        "Order now</a><a href='https://billing.racknerd.com/cart.php?a=add&pid=101'>Buy</a>",
        1,
    )
    assert len(racknerd.parse(page)) == 2


def test_currency_and_no_invented_cycle(html):
    page = html("cloudcone.html").replace("US$16.99 / yr", "EUR 16.99 / yr")
    assert parse_cards(page, "Test", "https://example.com")[0].currency == "EUR"
    page = html("cloudcone.html").replace("US$16.99 / yr", "$16.99")
    assert len(cloudcone.parse(page)) == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Renewal price is the same", True),
        ("Same price on renewal", True),
        ("Recurring discount", True),
        ("Renews at regular price", False),
        ("First year only", False),
        ("Sale!", None),
    ],
)
def test_renewal_policy(text, expected):
    assert renewal_policy(text) is expected


@pytest.mark.parametrize("provider", [racknerd, cloudcone])
def test_fetch_uses_provider_source(monkeypatch, html, provider):
    class Response:
        text = html(provider.__name__.rsplit(".", 1)[1] + ".html")

    urls = []
    monkeypatch.setattr(provider.requester, "get", lambda url: urls.append(url) or Response())
    assert len(provider.fetch()) == 2
    assert urls == [provider.SOURCE_URL]
