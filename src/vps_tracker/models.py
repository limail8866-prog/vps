from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite
from typing import Literal

BillingCycle = Literal[
    "monthly", "quarterly", "semiannually", "annually", "biennially", "triennially"
]
MONTHS: dict[str, int] = {
    "monthly": 1,
    "quarterly": 3,
    "semiannually": 6,
    "annually": 12,
    "biennially": 24,
    "triennially": 36,
}


@dataclass(frozen=True)
class Plan:
    provider: str
    name: str
    cpu: int
    ram_gb: float
    disk_gb: float
    bandwidth_tb: float
    price: Decimal
    currency: str
    billing_cycle: BillingCycle
    renewal_same: bool | None
    url: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        if self.billing_cycle not in MONTHS:
            raise ValueError(f"不支持的付款周期：{self.billing_cycle}")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("价格必须为有限正数")
        if self.cpu < 1 or any(
            not isfinite(value) or value <= 0
            for value in (self.ram_gb, self.disk_gb, self.bandwidth_tb)
        ):
            raise ValueError("套餐配置必须为正数")
        if self.fetched_at.tzinfo is None:
            raise ValueError("抓取时间必须包含时区")

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "name": self.name,
            "cpu": self.cpu,
            "ram_gb": self.ram_gb,
            "disk_gb": self.disk_gb,
            "bandwidth_tb": self.bandwidth_tb,
            "price": str(self.price),
            "currency": self.currency,
            "billing_cycle": self.billing_cycle,
            "renewal_same": self.renewal_same,
            "url": self.url,
            "fetched_at": self.fetched_at.isoformat(),
        }
