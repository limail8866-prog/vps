from datetime import UTC, datetime
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from ..http import requester
from ..models import Plan
from .common import ParseError, _parse_card
from .fallback import fetch_from_sources

SOURCE_URL = "https://dedirock.com/"


def _vps_link(href: str) -> bool:
    parsed = urlsplit(href)
    return parsed.hostname == "billing.dedirock.com" and any(
        part in parsed.path
        for part in (
            "/store/kvm-vps-hosting/",
            "/store/buffalo-kvm-vps/",
            "/store/vps-storage/",
            "/store/the-i9-dream/",
        )
    )


def parse(html: str, source_url: str = SOURCE_URL) -> list[Plan]:
    soup = BeautifulSoup(html, "html.parser")
    stamp = datetime.now(UTC)
    plans = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if not _vps_link(href) or href in plans:
            continue
        for ancestor in anchor.parents:
            if not isinstance(ancestor, Tag) or ancestor.name in {"body", "html"}:
                break
            urls = {
                str(a["href"])
                for a in ancestor.find_all("a", href=True)
                if _vps_link(str(a["href"]))
            }
            if len(urls) > 1:
                break
            counter = ancestor.select_one(".elementor-counter")
            if not counter:
                continue
            card = BeautifulSoup(str(ancestor), "html.parser")
            counter = card.select_one(".elementor-counter")
            number = counter.select_one("[data-to-value]")
            prefix = counter.select_one(".elementor-counter-number-prefix")
            cycle = counter.select_one(".elementor-counter-title")
            if not number or not prefix or not cycle:
                continue
            price_text = (
                f"{prefix.get_text(strip=True)}{number['data-to-value']} "
                f"{cycle.get_text(strip=True)}"
            )
            counter.clear()
            counter.string = price_text
            try:
                plans[href] = _parse_card(card, "DediRock", href, stamp)
                break
            except ValueError:
                continue
    if not plans:
        raise ParseError("DediRock 未解析出有效 VPS 套餐；动画价格、配置或页面结构可能变更")
    return list(plans.values())


def fetch() -> list[Plan]:
    return fetch_from_sources("dedirock", parse, requester)
