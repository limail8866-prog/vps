import logging
import re
from dataclasses import replace

from bs4 import BeautifulSoup

from ..config import get_config
from ..http import requester
from ..models import Plan
from .common import parse_cards
from .fallback import fetch_from_sources

SOURCE_URL = "https://cloudcone.com/vps/"
LOG = logging.getLogger(__name__)


def parse_renewal_rules(html: str) -> str | None:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    # 同周期续约不等于同价。条款允许涨价时保留 renewal_same=None。
    if (
        re.search(r"automatically\s+renew\s+for\s+the\s+same\s+length", text, re.I)
        and re.search(r"may\s+increase\s+its\s+fees", text, re.I)
        and re.search(r"forty-five\s*\(45\)\s+days", text, re.I)
    ):
        return "同周期自动续费；可提前45天通知调整费用（无锁价保证）"
    return None


def parse(html: str, source_url: str = SOURCE_URL) -> list[Plan]:
    return parse_cards(html, "CloudCone", source_url)


def fetch() -> list[Plan]:
    plans = fetch_from_sources("cloudcone", parse, requester)
    for url in get_config().renewal_sources:
        try:
            note = parse_renewal_rules(requester.get(url).text)
            if note:
                return [
                    replace(plan, renewal_note=note, renewal_url=url)
                    if plan.renewal_same is None
                    else plan
                    for plan in plans
                ]
        except Exception as exc:
            LOG.warning("CloudCone 续费规则来源失败：%s：%s", url, exc)
    return plans
