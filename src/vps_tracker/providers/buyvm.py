import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..http import requester
from ..models import Plan
from .common import ParseError, _parse_card
from .fallback import fetch_from_sources

SOURCE_URL = "https://buyvm.net/kvm-dedicated-server-slices/"


def parse_stock(script: str) -> dict:
    assignment = re.search(r"\bvar\s+plans\s*=", script)
    if assignment is None:
        raise ParseError("BuyVM 库存脚本缺少 plans 对象")
    start = script.find("{", assignment.end())
    if start == -1:
        raise ParseError("BuyVM 库存脚本缺少 JSON 数据")
    try:
        stock, _ = json.JSONDecoder().raw_decode(script[start:])
    except ValueError as exc:
        raise ParseError("BuyVM 库存脚本中的 plans 不再是有效 JSON") from exc
    if not isinstance(stock, dict) or not isinstance(stock.get("slice"), dict):
        raise ParseError("BuyVM 库存 JSON 缺少 slice")
    return stock["slice"]


def parse(html: str, stock_script: str, source_url: str = SOURCE_URL) -> list[Plan]:
    soup = BeautifulSoup(html, "html.parser")
    stock = parse_stock(stock_script)
    stamp = datetime.now(UTC)
    plans = {}
    for anchor in soup.select("a.orderbutton[data-group='slice'][data-plan]"):
        code = str(anchor["data-plan"])
        card = anchor.find_parent("div", class_="plan") or anchor.find_parent("tr")
        if card is None or code not in stock:
            continue
        for location in stock[code]:
            disabled = location.get("disabled")
            if disabled is True or disabled == "true":
                continue
            if disabled is not False and disabled != "false":
                raise ParseError("BuyVM 库存状态不明确")
            url = location["url"]
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "my.frantech.ca":
                raise ParseError("BuyVM 库存提供了不支持的购买地址")
            if url in plans:
                continue
            plan = _parse_card(card, "BuyVM", url, stamp)
            plans[url] = replace(plan, name=f"SLICE {code} — {location['location']}")
    if not plans:
        raise ParseError("BuyVM 暂无可售库存，或套餐/库存结构已变更")
    return list(plans.values())


def _fetch_page(html: str, source_url: str) -> list[Plan]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.select_one("script[src*='/assets/js/plans.js']")
    if not script:
        raise ParseError("BuyVM 页面未引用库存脚本")
    script_url = urljoin(source_url, str(script["src"]))
    return parse(html, requester.get(script_url).text, source_url)


def fetch() -> list[Plan]:
    return fetch_from_sources("buyvm", _fetch_page, requester)
