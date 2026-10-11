import tomllib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
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


def load_config(path: Path | None = None) -> Config:
    explicit = path is not None
    path = path or Path.cwd() / "config.toml"
    if not path.exists():
        if explicit:
            raise FileNotFoundError(f"配置文件不存在：{path}")
        return Config()
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    sources = dict(DEFAULT_SOURCES)
    for provider, settings in data.get("providers", {}).items():
        if provider not in sources:
            raise ValueError(f"未注册的商家配置：{provider}")
        sources[provider] = _urls(settings["sources"])
    cloudcone = data.get("providers", {}).get("cloudcone", {})
    renewal = (
        _urls(cloudcone["renewal_sources"])
        if cloudcone.get("renewal_sources")
        else Config().renewal_sources
    )
    ranking, alerts = data.get("ranking", {}), data.get("alerts", {})
    minimum = float(ranking.get("min_ram_gb", 0))
    if minimum < 0 or minimum == float("inf") or minimum != minimum:
        raise ValueError("最低内存必须为有限非负数")
    sort_by = ranking.get("sort_by", "monthly_cny")
    if sort_by not in {"monthly_cny", "cny_per_gb"}:
        raise ValueError("排序方式必须为 monthly_cny 或 cny_per_gb")
    threshold = Decimal(str(alerts.get("threshold_cny", "20")))
    if not threshold.is_finite() or threshold <= 0:
        raise ValueError("提醒阈值必须为有限正数")
    return Config(sources, renewal, minimum, sort_by, bool(alerts.get("enabled", False)), threshold)
