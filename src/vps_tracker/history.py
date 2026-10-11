"""北京时间每日库存；商家失败时保留最后观测值，避免误报下架。"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .fx import Rates
from .models import MONTHS, Plan
from .storage import write_json
from .timezone import BEIJING


def plan_id(plan: Plan | dict) -> str:
    provider, url = (
        (plan.provider, plan.url) if isinstance(plan, Plan) else (plan["provider"], plan["url"])
    )
    parsed = urlsplit(url)
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query)
        if not key.startswith("utm_") and key not in {"aff", "ref", "token"}
    )
    canonical = urlunsplit(
        ("https", parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(query), "")
    )
    return f"{provider}|{canonical}"


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("plans"), list):
        raise ValueError(f"无效历史快照：{path}")
    if datetime.fromisoformat(value["generated_at"]).tzinfo is None:
        raise ValueError(f"历史快照时间缺少时区：{path}")
    for row in value["plans"]:
        plan_id(row)
        amount = Decimal(row["price"])
        if not amount.is_finite() or amount <= 0 or row["billing_cycle"] not in MONTHS:
            raise ValueError(f"无效历史价格：{path}")
    return value


def _previous(root: Path, day: str) -> tuple[dict | None, list[str]]:
    warnings = []
    candidates = sorted((root / "data/history").glob("*.json"), reverse=True)
    for path in candidates:
        if path.stem >= day:
            continue
        try:
            return _load(path), warnings
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as exc:
            warnings.append(str(exc))
    # 兼容升级前仅有 latest.json 的仓库，不伪造昨天数据。
    try:
        legacy = _load(root / "data/latest.json")
        if (
            legacy
            and datetime.fromisoformat(legacy["generated_at"])
            .astimezone(BEIJING)
            .date()
            .isoformat()
            < day
        ):
            return legacy, warnings
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as exc:
        warnings.append(str(exc))
    return None, warnings


def update_history(
    root: Path,
    plans: list[Plan],
    rates: Rates | None,
    successful: set[str],
    failures: dict[str, str],
    stamp: datetime,
    sources: dict | None = None,
) -> dict:
    stamp = stamp.astimezone(BEIJING)
    day = stamp.date().isoformat()
    previous, warnings = _previous(root, day)
    baseline_date = None
    if previous:
        baseline_date = datetime.fromisoformat(previous["generated_at"]).astimezone(BEIJING).date()
    comparable = baseline_date == stamp.date() - timedelta(days=1)
    old = {plan_id(row): row for row in previous["plans"]} if previous else {}
    current = {}
    selected_sources = {name: record["selected_url"] for name, record in (sources or {}).items()}
    for plan in plans:
        row = plan.to_dict()
        if plan.provider.lower() in selected_sources:
            row["source_url"] = selected_sources[plan.provider.lower()]
        row["monthly_cny"] = (
            str(plan.price * rates.cny_per_unit(plan.currency) / MONTHS[plan.billing_cycle])
            if rates and plan.currency in rates.rates
            else None
        )
        current[plan_id(plan)] = row
    changes = []

    def source_confirmed(row: dict) -> bool:
        name = row["provider"].lower()
        return name not in selected_sources or row.get("source_url") == selected_sources[name]

    if comparable:
        for key, row in current.items():
            before = old.get(key)
            if before is None:
                changes.append({"kind": "new", "plan": row})
            elif before["currency"] == row["currency"]:
                before_price = Decimal(before["price"]) / MONTHS[before["billing_cycle"]]
                after_price = Decimal(row["price"]) / MONTHS[row["billing_cycle"]]
                if before_price != after_price:
                    changes.append(
                        {
                            "kind": "price_drop"
                            if after_price < before_price
                            else "price_increase",
                            "plan": row,
                            "previous": before,
                            "change_percent": str((after_price / before_price - 1) * 100),
                        }
                    )
        for key, row in old.items():
            if key not in current and row["provider"] in successful and source_confirmed(row):
                changes.append({"kind": "removed", "plan": row})
    # 同一天重跑失败时仍保留今天较早的成功结果；对比基准始终为昨天。
    inventory = dict(old)
    today_path = root / "data/history" / f"{day}.json"
    try:
        today = _load(today_path)
        if today:
            inventory.update({plan_id(row): row for row in today["plans"]})
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as exc:
        warnings.append(str(exc))
    inventory = {
        key: row
        for key, row in inventory.items()
        if row["provider"] not in successful or not source_confirmed(row)
    }
    inventory.update(current)
    write_json(
        today_path,
        {
            "generated_at": stamp.isoformat(),
            "timezone": "Asia/Shanghai",
            "successful_providers": sorted(successful),
            "plans": list(inventory.values()),
            "failures": failures,
        },
    )
    return {
        "baseline_date": baseline_date.isoformat() if comparable else None,
        "events": changes,
        "warnings": warnings,
        "skipped_providers": sorted(
            {
                row["provider"]
                for key, row in old.items()
                if row["provider"] not in successful
                or (key not in current and not source_confirmed(row))
            }
        ),
    }
