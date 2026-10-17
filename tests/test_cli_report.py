import json
from datetime import UTC, datetime
from decimal import Decimal

from vps_tracker import cli
from vps_tracker.config import Config
from vps_tracker.fx import Rates


def rates():
    return Rates({"USD": Decimal(1), "CNY": Decimal(7)}, datetime.now(UTC))


def fail():
    raise RuntimeError("模拟商家故障")


def test_partial_failure_generates_real_report(monkeypatch, tmp_path, plan):
    monkeypatch.setattr(
        cli,
        "PROVIDERS",
        {
            "failed": fail,
            "ok": lambda: [
                plan(renewal_same=False, name="Special | Plan"),
                plan(name="Unknown"),
            ],
        },
    )
    monkeypatch.setattr(cli, "fetch_rates", lambda path: rates())
    assert cli.main(["run", "--output-dir", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "data/latest.json").read_text())
    assert len(data["plans"]) == 2
    assert data["plans"][0]["monthly_cny"] == "7"
    assert data["failures"]["failed"] == "RuntimeError: 模拟商家故障"
    reports = list((tmp_path / "reports").glob("*.md"))
    assert len(reports) == 1
    text = reports[0].read_text()
    assert "¥7.00" in text
    assert "⚠ 续费涨价" in text
    assert "未知（请核实）" in text
    assert "模拟商家故障" in text
    assert "Special \\| Plan" in text
    assert "## 续费涨价提醒" in text


def test_all_providers_fail_still_writes_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "PROVIDERS", {"one": fail, "two": fail})
    monkeypatch.setattr(cli, "fetch_rates", lambda path: rates())
    assert cli.run(tmp_path) == 1
    data = json.loads((tmp_path / "data/latest.json").read_text())
    assert data["plans"] == []
    assert set(data["failures"]) == {"one", "two"}


def test_fx_failure_preserves_unranked_plans(monkeypatch, tmp_path, plan):
    monkeypatch.setattr(cli, "PROVIDERS", {"one": lambda: [plan()]})
    monkeypatch.setattr(cli, "fetch_rates", lambda path: fail())
    assert cli.run(tmp_path) == 1
    data = json.loads((tmp_path / "data/latest.json").read_text())
    assert data["fx"] is None
    assert data["unranked_plans"][0]["price"] == "12"
    assert "fx" in data["failures"]


def test_missing_currency_does_not_block_other_plans(monkeypatch, tmp_path, plan):
    monkeypatch.setattr(cli, "PROVIDERS", {"one": lambda: [plan(), plan(currency="EUR")]})
    monkeypatch.setattr(cli, "fetch_rates", lambda path: rates())
    assert cli.run(tmp_path) == 0
    data = json.loads((tmp_path / "data/latest.json").read_text())
    assert len(data["plans"]) == 1
    assert data["unranked_plans"][0]["currency"] == "EUR"
    assert "fx/EUR" in data["failures"]


def test_empty_provider_is_reported_as_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "PROVIDERS", {"one": lambda: []})
    monkeypatch.setattr(cli, "fetch_rates", lambda path: rates())
    assert cli.run(tmp_path) == 1
    data = json.loads((tmp_path / "data/latest.json").read_text())
    assert "未返回任何可售套餐" in data["failures"]["one"]


def test_filter_does_not_remove_plans_from_historical_inventory(monkeypatch, tmp_path, plan):
    monkeypatch.setattr(
        cli, "PROVIDERS", {"one": lambda: [plan(), plan(ram_gb=2, url="https://example.com/large")]}
    )
    monkeypatch.setattr(cli, "fetch_rates", lambda path: rates())
    assert cli.run(tmp_path, Config(min_ram_gb=2, sort_by="cny_per_gb")) == 0
    data = json.loads((tmp_path / "data/latest.json").read_text())
    assert len(data["plans"]) == 1
    history = next((tmp_path / "data/history").glob("*.json"))
    assert len(json.loads(history.read_text())["plans"]) == 2
    assert "每 GB 内存月均价" in next((tmp_path / "reports").glob("*.md")).read_text()


def test_budget_filters_report_changes_but_keeps_inventory(monkeypatch, tmp_path, plan):
    from datetime import timedelta

    from vps_tracker.history import update_history
    from vps_tracker.timezone import BEIJING

    stamp = datetime.now(BEIJING)
    update_history(tmp_path, [], rates(), {"Example"}, {}, stamp - timedelta(days=1))
    monkeypatch.setattr(
        cli, "PROVIDERS", {"one": lambda: [plan(), plan(price=Decimal(120), url="https://a.test")]}
    )
    monkeypatch.setattr(cli, "fetch_rates", lambda path: rates())
    assert cli.run(tmp_path, Config(max_monthly_cny=Decimal(20))) == 0
    payload = json.loads((tmp_path / "data/latest.json").read_text())
    assert len(payload["plans"]) == len(payload["changes"]["events"]) == 1
    history = tmp_path / "data/history" / f"{stamp.date()}.json"
    assert len(json.loads(history.read_text())["plans"]) == 2


def test_budget_cli_overrides_config(monkeypatch, tmp_path, plan):
    path = tmp_path / "config.toml"
    path.write_text('[ranking]\nmax_monthly_cny = "1"')
    monkeypatch.setattr(cli, "PROVIDERS", {"one": lambda: [plan()]})
    monkeypatch.setattr(cli, "fetch_rates", lambda path: rates())
    assert (
        cli.main(
            ["run", "--config", str(path), "--output-dir", str(tmp_path), "--max-monthly-cny", "7"]
        )
        == 0
    )
    payload = json.loads((tmp_path / "data/latest.json").read_text())
    assert len(payload["plans"]) == 1
    assert payload["ranking"]["max_monthly_cny"] == "7"
