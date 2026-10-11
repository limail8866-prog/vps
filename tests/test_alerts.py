import json
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from vps_tracker.alerts import create_alerts, notify
from vps_tracker.config import Config
from vps_tracker.timezone import BEIJING


def payload(plan):
    return {
        "generated_at": datetime.now(BEIJING).isoformat(),
        "plans": [
            {**plan(price=Decimal(18)).to_dict(), "monthly_cny": "19.99"},
            {
                **plan(name="Equal", url="https://example.com/order?pid=2").to_dict(),
                "monthly_cny": "20",
            },
            {
                **plan(name="Above", url="https://example.com/order?pid=3").to_dict(),
                "monthly_cny": "20.01",
            },
        ],
    }


def test_strict_threshold_and_deduplication_even_closed_issue(plan):
    issues, posts = [], []

    def handler(request):
        if request.method == "GET":
            assert request.url.params["state"] == "all"
            return httpx.Response(200, json=issues)
        body = json.loads(request.content)
        posts.append(body)
        issues.append({"body": body["body"], "state": "closed"})
        return httpx.Response(201, json={"html_url": "https://github.com/org/repo/issues/1"})

    data = payload(plan)
    with httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    ) as client:
        assert create_alerts(data, "org/repo", Decimal(20), client) == 1
        assert create_alerts(data, "org/repo", Decimal("20.0"), client) == 0
    assert len(posts) == 1
    assert "¥19.99" in posts[0]["title"]
    assert "vps-alert:" in posts[0]["body"]


def test_pagination_finds_existing_marker(plan):
    posted = []
    data = payload(plan)
    marker = []

    def first(request):
        if request.method == "GET":
            return httpx.Response(200, json=[])
        marker.append(json.loads(request.content)["body"])
        return httpx.Response(201, json={})

    with httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(first)
    ) as client:
        create_alerts(data, "org/repo", Decimal(20), client)

    def second(request):
        if request.method == "POST":
            posted.append(request)
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json=[{"body": "irrelevant"}] * 100)
        return httpx.Response(200, json=[{"body": marker[0]}])

    with httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(second)
    ) as client:
        assert create_alerts(data, "org/repo", Decimal(20), client) == 0
    assert posted == []


def test_stale_report_never_creates_issues(plan):
    data = payload(plan)
    data["generated_at"] = (datetime.now(BEIJING) - timedelta(days=1)).isoformat()
    with httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(
            lambda request: pytest.fail("过期报告不应请求 GitHub"),
        ),
    ) as client:
        with pytest.raises(ValueError, match="过期"):
            create_alerts(data, "org/repo", Decimal(20), client)


def test_no_candidates_never_requests_github(plan):
    with httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(
            lambda request: pytest.fail("没有候选套餐不应请求 GitHub"),
        ),
    ) as client:
        assert create_alerts(payload(plan), "org/repo", Decimal(1), client) == 0


def test_disabled_alerts_do_not_require_credentials(tmp_path):
    assert notify(tmp_path / "missing.json", "org/repo", Config()) == 0


def test_missing_token_fails_with_actionable_error(monkeypatch, tmp_path):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ValueError, match="GH_TOKEN"):
        notify(tmp_path / "missing.json", "org/repo", replace(Config(), alerts_enabled=True))
