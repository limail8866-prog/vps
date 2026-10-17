import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from vps_tracker import cli
from vps_tracker.config import Config
from vps_tracker.fx import Rates
from vps_tracker.rank import rank_plans
from vps_tracker.report import write_report
from vps_tracker.view import show


def snapshot(tmp_path, plan):
    fx = Rates({"USD": Decimal(1), "CNY": Decimal(7)}, datetime(2026, 1, 1, tzinfo=UTC))
    ranked = rank_plans([plan(name="Small"), plan(name="Large", price=Decimal(48), ram_gb=8)], fx)
    write_report(tmp_path, ranked, fx, {}, datetime(2026, 1, 1, tzinfo=UTC))
    return tmp_path / "data/latest.json"


def test_offline_show_filters_without_changing_files(tmp_path, plan):
    path = snapshot(tmp_path, plan)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    text = show(path, Config(max_monthly_cny=Decimal(20)))
    assert "[Small]" in text and "[Large]" not in text
    assert "月均价 ≤ ¥20" in text
    assert "2026-01-01" in text and "未重新抓取" in text
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_show_cli_sort_override(tmp_path, plan, capsys):
    path = snapshot(tmp_path, plan)
    assert cli.main(["show", "--input", str(path), "--sort", "cny_per_gb"]) == 0
    output = capsys.readouterr().out
    assert output.index("[Large]") < output.index("[Small]")


def test_filtered_snapshot_explains_unavailable_inventory(tmp_path, plan):
    path = snapshot(tmp_path, plan)
    payload = json.loads(path.read_text())
    payload["ranking"] = {"min_ram_gb": 2, "max_monthly_cny": "20"}
    path.write_text(json.dumps(payload))
    assert "扩大范围请重新运行 run" in show(path, Config())


@pytest.mark.parametrize("payload", ["{}", "[]", "broken", '{"generated_at": "2026-01-01"}'])
def test_bad_snapshot_has_actionable_error(tmp_path, payload):
    path = tmp_path / "latest.json"
    path.write_text(payload)
    with pytest.raises(ValueError, match="请先运行 run"):
        show(path, Config())


def test_invalid_config_cli_has_no_traceback(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('[alerts]\nenabled = "false"')
    with pytest.raises(SystemExit) as error:
        cli.main(["show", "--config", str(path)])
    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert "布尔值" in stderr and "Traceback" not in stderr
