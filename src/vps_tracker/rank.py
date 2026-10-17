from dataclasses import dataclass
from decimal import Decimal

from .config import Config, decimal_value
from .fx import Rates
from .models import MONTHS, Plan


@dataclass(frozen=True)
class RankedPlan:
    plan: Plan
    monthly_cny: Decimal

    @property
    def cny_per_gb(self) -> Decimal:
        return self.monthly_cny / Decimal(str(self.plan.ram_gb))

    def to_dict(self) -> dict:
        return {
            **self.plan.to_dict(),
            "monthly_cny": str(self.monthly_cny),
            "cny_per_gb": str(self.cny_per_gb),
        }


def select_plans(
    ranked: list[RankedPlan],
    min_ram_gb: float = 0,
    sort_by: str = "monthly_cny",
    max_monthly_cny: Decimal | None = None,
) -> list[RankedPlan]:
    if min_ram_gb < 0 or min_ram_gb != min_ram_gb or min_ram_gb == float("inf"):
        raise ValueError("最低内存必须为有限非负数")
    if sort_by not in {"monthly_cny", "cny_per_gb"}:
        raise ValueError("无效的排序方式")
    if max_monthly_cny is not None:
        max_monthly_cny = decimal_value(max_monthly_cny, "月均预算上限")
    return sorted(
        (
            row
            for row in ranked
            if row.plan.ram_gb >= min_ram_gb
            and (max_monthly_cny is None or row.monthly_cny <= max_monthly_cny)
        ),
        key=lambda row: (getattr(row, sort_by), row.monthly_cny, row.plan.provider, row.plan.name),
    )


def rank_plans(plans: list[Plan], rates: Rates) -> list[RankedPlan]:
    ranked = [
        RankedPlan(
            plan, plan.price * rates.cny_per_unit(plan.currency) / MONTHS[plan.billing_cycle]
        )
        for plan in plans
    ]
    return sorted(ranked, key=lambda row: (row.monthly_cny, row.plan.provider, row.plan.name))


def ranking_options(config: Config) -> dict:
    return {
        "min_ram_gb": config.min_ram_gb,
        "sort_by": config.sort_by,
        "max_monthly_cny": str(config.max_monthly_cny)
        if config.max_monthly_cny is not None
        else None,
    }


def filter_changes(changes: dict | None, config: Config) -> dict | None:
    if changes is None:
        return None
    return {
        **changes,
        "events": [
            event
            for event in changes["events"]
            if event["plan"]["ram_gb"] >= config.min_ram_gb
            and (
                config.max_monthly_cny is None
                or (
                    event["plan"].get("monthly_cny") is not None
                    and Decimal(event["plan"]["monthly_cny"]) <= config.max_monthly_cny
                )
            )
        ],
    }
