import json
from datetime import UTC, datetime
from decimal import Decimal

from vps_tracker.fx import Rates
from vps_tracker.history import plan_id, update_history
from vps_tracker.rank import rank_plans
from vps_tracker.report import write_report


def rates(cny="7"):
    return Rates({"USD": Decimal(1), "CNY": Decimal(cny)}, datetime.now(UTC))


def stamp(day):
    return datetime(2026, 1, day, 2, tzinfo=UTC)


def test_price_drop_new_removal_and_failed_provider_inventory(tmp_path, plan):
    old = plan(url="https://example.com/order?pid=1")
    removed = plan(name="Gone", url="https://example.com/order?pid=2")
    offline = plan(provider="Offline", url="https://offline.com/order?pid=3")
    first = update_history(
        tmp_path, [old, removed, offline], rates(), {"Example", "Offline"}, {}, stamp(1)
    )
    assert first["baseline_date"] is None
    assert first["events"] == []
    cheaper = plan(price=Decimal(6), url=old.url)
    new = plan(name="New", url="https://example.com/order?pid=4")
    changes = update_history(
        tmp_path, [cheaper, new], rates(), {"Example"}, {"offline": "403"}, stamp(2)
    )
    assert changes["baseline_date"] == "2026-01-01"
    assert {e["kind"] for e in changes["events"]} == {"price_drop", "new", "removed"}
    assert (
        next(e for e in changes["events"] if e["kind"] == "price_drop")["change_percent"] == "-50.0"
    )
    assert changes["skipped_providers"] == ["Offline"]
    snapshot = json.loads((tmp_path / "data/history/2026-01-02.json").read_text())
    assert {row["name"] for row in snapshot["plans"]} == {old.name, new.name}
    assert any(row["provider"] == "Offline" for row in snapshot["plans"])
    # 同一天重跑不把上一次运行当作前一天。
    repeat = update_history(tmp_path, [cheaper, new], rates(), {"Example"}, {}, stamp(2))
    assert repeat["events"] == changes["events"]
    recovered = update_history(
        tmp_path, [cheaper, new, offline], rates(), {"Example", "Offline"}, {}, stamp(3)
    )
    assert recovered["events"] == []


def test_exchange_rate_change_is_not_provider_price_drop(tmp_path, plan):
    update_history(tmp_path, [plan()], rates("7"), {"Example"}, {}, stamp(1))
    changes = update_history(tmp_path, [plan()], rates("6"), {"Example"}, {}, stamp(2))
    assert changes["events"] == []


def test_same_monthly_cost_different_billing_cycle_is_not_price_change(tmp_path, plan):
    update_history(tmp_path, [plan()], rates(), {"Example"}, {}, stamp(1))
    changes = update_history(
        tmp_path,
        [plan(price=Decimal(1), billing_cycle="monthly")],
        rates(),
        {"Example"},
        {},
        stamp(2),
    )
    assert changes["events"] == []


def test_gap_in_history_is_not_claimed_to_be_yesterday(tmp_path, plan):
    update_history(tmp_path, [plan()], rates(), {"Example"}, {}, stamp(1))
    changes = update_history(tmp_path, [], rates(), set(), {}, stamp(3))
    assert changes["baseline_date"] is None
    assert changes["events"] == []
    assert len(json.loads((tmp_path / "data/history/2026-01-03.json").read_text())["plans"]) == 1


def test_first_partial_run_of_the_day_does_not_erase_earlier_success(tmp_path, plan):
    update_history(tmp_path, [plan()], rates(), {"Example"}, {}, stamp(1))
    update_history(tmp_path, [], rates(), set(), {"example": "offline"}, stamp(1))
    assert len(json.loads((tmp_path / "data/history/2026-01-01.json").read_text())["plans"]) == 1


def test_corrupt_snapshot_reports_warning_not_false_removal(tmp_path, plan):
    history = tmp_path / "data/history"
    history.mkdir(parents=True)
    (history / "2026-01-01.json").write_text("bad")
    changes = update_history(tmp_path, [plan()], rates(), {"Example"}, {}, stamp(2))
    assert changes["warnings"]
    assert changes["baseline_date"] is None
    assert changes["events"] == []


def test_tracking_token_does_not_change_plan_identity(plan):
    assert plan_id(plan(url="https://example.com/vps/1/create?token=foo&utm_source=x")) == plan_id(
        plan(url="https://example.com/vps/1/create?token=bar")
    )


def test_fallback_to_different_page_does_not_mark_previous_offers_removed(tmp_path, plan):
    original = plan(url="https://example.com/order?pid=1")
    fallback = plan(url="https://example.com/order?pid=2", name="Fallback")
    first = {"example": {"selected_url": "https://example.com/primary"}}
    second = {"example": {"selected_url": "https://example.com/backup"}}
    update_history(tmp_path, [original], rates(), {"Example"}, {}, stamp(1), first)
    changes = update_history(tmp_path, [fallback], rates(), {"Example"}, {}, stamp(2), second)
    assert [e["kind"] for e in changes["events"]] == ["new"]
    assert changes["skipped_providers"] == ["Example"]
    snapshot = json.loads((tmp_path / "data/history/2026-01-02.json").read_text())
    assert len(snapshot["plans"]) == 2
    changes = update_history(tmp_path, [fallback], rates(), {"Example"}, {}, stamp(3), second)
    assert changes["events"] == []
    # 主来源恢复并成功抓取后，才可以确认它的旧套餐已不在页面中。
    changes = update_history(tmp_path, [fallback], rates(), {"Example"}, {}, stamp(4), first)
    assert any(
        e["kind"] == "removed" and e["plan"]["url"] == original.url for e in changes["events"]
    )
    assert plan_id(plan(url="https://example.com/cart.php?pid=1")) != plan_id(
        plan(url="https://example.com/cart.php?pid=2")
    )


def test_beijing_date_boundary_and_minimal_published_rates(tmp_path, plan):
    fx = Rates(
        {"USD": Decimal(1), "CNY": Decimal(7), "EUR": Decimal("0.9"), "JPY": Decimal(150)}, stamp(1)
    )
    ranked = rank_plans([plan(), plan(currency="EUR")], fx)
    report, data = write_report(tmp_path, ranked, fx, {}, datetime(2026, 1, 1, 23, tzinfo=UTC))
    assert report.name == "2026-01-02.md"
    assert "（北京时间）" in report.read_text()
    payload = json.loads(data.read_text())
    assert payload["timezone"] == "Asia/Shanghai"
    assert payload["generated_at"].startswith("2026-01-02T07:00:00+08:00")
    assert set(payload["fx"]["rates"]) == {"USD", "CNY", "EUR"}
