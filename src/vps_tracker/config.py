import tomllib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_SOURCES = {
    "racknerd": (
        "https://www.racknerd.com/specials/",
        "https://www.racknerd.com/NewYear/",
        "https://www.racknerd.com/BlackFriday/",
    ),
    "cloudcone": ("https://cloudcone.com/vps/",),
    "dedirock": (
        "https://dedirock.com/",
        "https://dedirock.com/kvm-vps-los-angeles/",
        "https://dedirock.com/kvm-vps-buffalo/",
    ),
    "buyvm": ("https://buyvm.net/kvm-dedicated-server-slices/",),
}


@dataclass(frozen=True)
class Config:
    sources: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_SOURCES))
    renewal_sources: tuple[str, ...] = ("https://cloudcone.com/policies/terms/",)
    min_ram_gb: float = 0
    sort_by: str = "monthly_cny"
    alerts_enabled: bool = False
    alert_threshold_cny: Decimal = Decimal("20")
    max_monthly_cny: Decimal | None = None

    def __post_init__(self) -> None:
        minimum = decimal_value(self.min_ram_gb, "最低内存", allow_zero=True)
        if not float(minimum) < float("inf"):
            raise ValueError("最低内存必须为有限非负数")
        if not isinstance(self.sort_by, str) or self.sort_by not in {"monthly_cny", "cny_per_gb"}:
            raise ValueError("排序方式必须为 monthly_cny 或 cny_per_gb")
        if not isinstance(self.alerts_enabled, bool):
            raise ValueError("alerts.enabled 必须为布尔值 true 或 false，不能加引号")
        decimal_value(self.alert_threshold_cny, "提醒阈值")
        if self.max_monthly_cny is not None:
            decimal_value(self.max_monthly_cny, "月均预算上限")


active_config: ContextVar[Config | None] = ContextVar("vps_config", default=None)


def get_config() -> Config:
    return active_config.get() or Config()


@contextmanager
def using_config(config: Config):
    token = active_config.set(config)
    try:
        yield
    finally:
        active_config.reset(token)


def _urls(values) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise ValueError("来源必须是非空 HTTPS 地址列表")
    for url in values:
        if isinstance(url, str) and (urlsplit(url).username or urlsplit(url).password):
            raise ValueError("来源地址不可包含用户名或凭据")
        if (
            not isinstance(url, str)
            or urlsplit(url).scheme != "https"
            or not urlsplit(url).hostname
        ):
            raise ValueError(f"来源必须为完整 HTTPS 地址：{url}")
    return tuple(values)


def decimal_value(value, label: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}必须为有效数字") from exc
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        kind = "非负数" if allow_zero else "正数"
        raise ValueError(f"{label}必须为有限{kind}")
    return number


def _table(value, label: str, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label}必须为 TOML 配置表")
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f"{label}存在未知配置项：{', '.join(sorted(unknown))}")
    return value


def load_config(path: Path | None = None) -> Config:
    explicit = path is not None
    path = path or Path.cwd() / "config.toml"
    if not path.exists():
        if explicit:
            raise FileNotFoundError(f"配置文件不存在：{path}")
        return Config()
    with path.open("rb") as stream:
        data = _table(tomllib.load(stream), "配置", {"providers", "ranking", "alerts"})
    sources = dict(DEFAULT_SOURCES)
    providers = _table(data.get("providers", {}), "providers", set(sources))
    renewal = Config().renewal_sources
    for provider, settings in providers.items():
        allowed = {"sources", "renewal_sources"} if provider == "cloudcone" else {"sources"}
        settings = _table(settings, f"providers.{provider}", allowed)
        if "sources" in settings:
            sources[provider] = _urls(settings["sources"])
        if "renewal_sources" in settings:
            renewal = _urls(settings["renewal_sources"])
    ranking = _table(
        data.get("ranking", {}), "ranking", {"min_ram_gb", "sort_by", "max_monthly_cny"}
    )
    alerts = _table(data.get("alerts", {}), "alerts", {"enabled", "threshold_cny"})
    minimum = decimal_value(ranking.get("min_ram_gb", 0), "最低内存", allow_zero=True)
    budget = ranking.get("max_monthly_cny")
    return Config(
        sources=sources,
        renewal_sources=renewal,
        min_ram_gb=float(minimum),
        sort_by=ranking.get("sort_by", "monthly_cny"),
        alerts_enabled=alerts.get("enabled", False),
        alert_threshold_cny=decimal_value(alerts.get("threshold_cny", "20"), "提醒阈值"),
        max_monthly_cny=decimal_value(budget, "月均预算上限") if budget is not None else None,
    )
