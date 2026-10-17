"""读取已经生成的快照；不访问网络、不改写报告或历史。"""

import json
from datetime import datetime
from pathlib import Path

from .config import Config, decimal_value
from .fx import Rates, validate_rates
from .models import Plan
from .rank import RankedPlan, filter_changes, ranking_options, select_plans
from .report import render_report


def _plan(row: dict) -> Plan:
    fields = {key: row[key] for key in Plan.__dataclass_fields__ if key in row}
    fields["price"] = decimal_value(row["price"], "快照价格")
    fields["fetched_at"] = datetime.fromisoformat(row["fetched_at"])
    return Plan(**fields)


def show(path: Path, config: Config) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stamp = datetime.fromisoformat(payload["generated_at"])
        if stamp.tzinfo is None:
            raise ValueError("快照生成时间缺少时区")
        rows = [
            RankedPlan(_plan(row), decimal_value(row["monthly_cny"], "快照月均价"))
            for row in payload["plans"]
        ]
        fx = payload["fx"]
        rates = None
        if fx:
            if fx["base"] != "USD":
                raise ValueError("快照汇率基准不是 USD")
            fx_stamp = datetime.fromisoformat(fx["fetched_at"])
            if fx_stamp.tzinfo is None:
                raise ValueError("快照汇率时间缺少时区")
            rates = Rates(validate_rates(fx["rates"]), fx_stamp, fx["cached"], fx.get("warning"))
        rows = select_plans(rows, config.min_ram_gb, config.sort_by, config.max_monthly_cny)
        report = render_report(
            rows,
            rates,
            payload["failures"],
            stamp,
            [_plan(row) for row in payload.get("unranked_plans", [])],
            filter_changes(payload.get("changes"), config),
            ranking_options(config),
            payload.get("sources"),
        )
        original = payload.get("ranking") or {}
        notes = ["离线查看：使用快照生成时的价格和汇率，未重新抓取。"]
        if original.get("min_ram_gb", 0) or original.get("max_monthly_cny") is not None:
            notes.append(
                "原始快照已筛选：内存 ≥ "
                f"{original.get('min_ram_gb', 0)} GB，月均预算上限 "
                f"{original.get('max_monthly_cny') or '不限'}；"
                "本次只能在已保存套餐中筛选，扩大范围请重新运行 run。"
            )
        return report + "\n" + "\n".join(notes) + "\n"
    except (ValueError, KeyError, TypeError, ArithmeticError, AttributeError) as exc:
        raise ValueError(f"无法读取有效快照 {path}：{exc}；请先运行 run 生成报告") from exc
