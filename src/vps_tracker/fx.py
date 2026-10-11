import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .http import Requester, requester
from .storage import write_json

FX_URL = "https://open.er-api.com/v6/latest/USD"


@dataclass(frozen=True)
class Rates:
    rates: dict[str, Decimal]
    fetched_at: datetime
    cached: bool = False
    warning: str | None = None

    def cny_per_unit(self, currency: str) -> Decimal:
        return self.rates["CNY"] / self.rates[currency.upper()]

    def to_dict(self, currencies: Iterable[str] | None = None) -> dict:
        selected = set(self.rates) if currencies is None else {"USD", "CNY", *currencies}
        return {
            "base": "USD",
            "rates": {key: str(self.rates[key]) for key in sorted(selected) if key in self.rates},
            "fetched_at": self.fetched_at.isoformat(),
            "cached": self.cached,
            "warning": self.warning,
        }


def validate_rates(values: dict) -> dict[str, Decimal]:
    if not isinstance(values, dict):
        raise ValueError("汇率必须为币种到数值的字典")
    rates = {key: Decimal(str(value)) for key, value in values.items()}
    if rates.get("USD") != 1 or "CNY" not in rates:
        raise ValueError("汇率缺少 CNY 或基准不是 USD=1")
    if any(not value.is_finite() or value <= 0 for value in rates.values()):
        raise ValueError("汇率必须为有限正数")
    return rates


def fetch_rates(cache_path: Path, http: Requester = requester) -> Rates:
    try:
        payload = http.get(FX_URL).json()
        if payload.get("result") != "success" or payload.get("base_code") != "USD":
            raise ValueError("汇率服务未返回 USD 基准成功结果")
        rates = Rates(validate_rates(payload["rates"]), datetime.now(UTC))
    except Exception as live_error:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload["base"] != "USD":
                raise ValueError("缓存汇率基准不是 USD")
            stamp = datetime.fromisoformat(payload["fetched_at"])
            if stamp.tzinfo is None:
                raise ValueError("缓存时间缺少时区")
            return Rates(
                validate_rates(payload["rates"]),
                stamp,
                True,
                f"实时汇率失败，使用缓存：{type(live_error).__name__}: {live_error}",
            )
        except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as cache_error:
            raise RuntimeError(
                f"汇率获取失败且无有效缓存；实时：{live_error}；缓存：{cache_error}"
            ) from live_error
    try:
        write_json(cache_path, rates.to_dict())
    except OSError as exc:
        return Rates(rates.rates, rates.fetched_at, warning=f"汇率缓存写入失败：{exc}")
    return rates
