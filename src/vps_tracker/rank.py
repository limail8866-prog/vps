from dataclasses import dataclass
from decimal import Decimal

from .fx import Rates
from .models import MONTHS, Plan


@dataclass(frozen=True)
class RankedPlan:
    plan: Plan
    monthly_cny: Decimal

    def to_dict(self) -> dict:
        return {**self.plan.to_dict(), "monthly_cny": str(self.monthly_cny)}


def rank_plans(plans: list[Plan], rates: Rates) -> list[RankedPlan]:
    ranked = [
        RankedPlan(
            plan, plan.price * rates.cny_per_unit(plan.currency) / MONTHS[plan.billing_cycle]
        )
        for plan in plans
    ]
    return sorted(ranked, key=lambda row: (row.monthly_cny, row.plan.provider, row.plan.name))
