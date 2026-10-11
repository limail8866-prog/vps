"""解析服务端套餐卡片；不能确认价格/周期/配置时拒绝猜测。"""

import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from ..models import BillingCycle, Plan


class ParseError(ValueError):
    pass


PRICE = re.compile(
    r"(?P<currency>US\$|USD|EUR|GBP|CNY|RMB|[$€£¥])\s*"
    r"(?P<price>\d+(?:\.\d+)?)\s*(?:/|per\s+)?\s*"
    r"(?P<cycle>biennially|triennially|semiannually|quarterly|annually|annual|"
    r"yearly|monthly|month|year|yr|mo)\b",
    re.I,
)
CYCLES: dict[str, BillingCycle] = {
    "mo": "monthly",
    "month": "monthly",
    "monthly": "monthly",
    "yr": "annually",
    "year": "annually",
    "yearly": "annually",
    "annual": "annually",
    "annually": "annually",
    "quarterly": "quarterly",
    "semiannually": "semiannually",
    "biennially": "biennially",
    "triennially": "triennially",
}
CURRENCIES = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "CNY", "RMB": "CNY"}


def renewal_policy(text: str) -> bool | None:
    if re.search(
        r"first\s+(?:year|term|month)\s+only|renew(?:al|s)?\s+(?:at\s+)?"
        r"(?:the\s+)?(?:regular|higher|standard)\s+price|introductory\s+price",
        text,
        re.I,
    ):
        return False
    if re.search(
        r"renew(?:al|s)?\s+(?:price\s+)?(?:is\s+|at\s+)?(?:the\s+)?same|"
        r"(?:same|locked)\s+(?:price\s+)?(?:on|for|at)\s+renewal|"
        r"recurring\s+(?:discount|price)|price\s+for\s+life",
        text,
        re.I,
    ):
        return True
    return None


def _amount(text: str, label: str, divisor: float) -> float:
    unit_value = r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>MB|GB|TB)(?:/Mo(?:nth)?)?"
    # 先匹配显式冒号，防止 RAM: 2048 MB Storage: 50 GB 跨字段误配。
    match = re.search(r"(?:" + label + r")\s*:\s*" + unit_value, text, re.I)
    if match is None:
        match = re.search(unit_value + r"\s*(?:of\s+)?(?:" + label + r")\b(?!\s*:)", text, re.I)
    if match is None:
        raise ParseError(f"缺少配置：{label}")
    value = float(match["value"])
    unit = match["unit"].upper()
    if divisor == 1000:  # 网络流量按十进制，GB / 1000 = TB
        return value * {"MB": 0.000001, "GB": 0.001, "TB": 1}[unit]
    return value * {"MB": 1 / 1024, "GB": 1, "TB": 1024}[unit]


def _text(card: Tag) -> str:
    # 排除划掉的原价以及脚本，避免把原价当促销价。
    clean = BeautifulSoup(str(card), "html.parser")
    for ignored in clean.select("del, s, strike, script, style"):
        ignored.decompose()
    text = " ".join(clean.stripped_strings)
    return re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", text)


def _order_link(anchor: Tag) -> bool:
    href = str(anchor.get("href", ""))
    host = urlsplit(href).hostname or ""
    return ("cart.php" in href and ("pid=" in href or "id=" in href)) or (
        host == "app.cloudcone.com" and any(part in href for part in ("/compute/", "/vps/"))
    )


def _parse_card(card: Tag, provider: str, url: str, stamp: datetime) -> Plan:
    text = _text(card)
    if re.search(r"sold\s*out|out\s+of\s+stock|unavailable", text, re.I):
        raise ParseError("套餐已售罄")
    billed = re.search(r"\bBilled\s+", text, re.I)
    price = PRICE.match(text, billed.end()) if billed else PRICE.search(text)
    if price is None:
        raise ParseError("缺少带币种和付款周期的价格")
    cpu = re.search(r"(\d+)\s*(?:x\s*)?(?:vCPU|vCore|CPU|(?:virtual\s+)?cores?)\b", text, re.I)
    if cpu is None:
        cpu = re.search(r"(?:vCPU|CPU|cores?)\s*:?\s*(\d+)", text, re.I)
    if cpu is None:
        raise ParseError("缺少 CPU 核数")
    ram = _amount(text, r"(?:(?:DDR\d|Dedicated)\s+)?(?:RAM|memory)", 1024)
    disk = _amount(text, r"(?:(?:NVMe|Pure)\s+)?(?:SSD|HDD|disk|storage|space)", 1024)
    bandwidth = (
        None
        if re.search(r"unmetered\s+bandwidth|unlim\.", text, re.I)
        else _amount(text, r"(?:monthly\s+)?(?:bandwidth|transfer|traffic)", 1000)
    )
    title = card.select_one("h2, h3, h4, .plan-name, .pricing-title, .pricing-header")
    name = " ".join(title.stripped_strings) if title else f"{ram:g} GB RAM / {disk:g} GB"
    marker = price["currency"].upper()
    return Plan(
        provider,
        name,
        int(cpu[1]),
        ram,
        disk,
        bandwidth,
        Decimal(price["price"]),
        CURRENCIES.get(marker, marker),
        CYCLES[price["cycle"].lower()],
        renewal_policy(text),
        url,
        stamp,
    )


def parse_cards(html: str, provider: str, source_url: str) -> list[Plan]:
    soup = BeautifulSoup(html, "html.parser")
    stamp = datetime.now(UTC)
    plans: dict[str, Plan] = {}
    errors: list[str] = []
    for anchor in soup.find_all("a", href=True):
        if not _order_link(anchor):
            continue
        url = urljoin(source_url, str(anchor["href"]))
        if url in plans or urlsplit(url).scheme != "https":
            continue
        last_error = "未找到套餐卡片"
        for card in anchor.parents:
            if not isinstance(card, Tag) or card.name in {"body", "html", "[document]"}:
                break
            links = {
                urljoin(source_url, str(link["href"]))
                for link in card.find_all("a", href=True)
                if _order_link(link)
            }
            if len(links) > 1:  # 不跨卡片拼接不同套餐的规格和价格
                break
            try:
                plans[url] = _parse_card(card, provider, url, stamp)
                break
            except (ParseError, ValueError) as exc:
                last_error = str(exc)
        else:
            last_error = "未找到套餐卡片"
        if url not in plans:
            errors.append(last_error)
    if not plans:
        reason = "; ".join(sorted(set(errors))) or "未找到可识别的下单链接"
        raise ParseError(f"{provider} 未解析出可售套餐，页面可能已变更：{reason}")
    return list(plans.values())
