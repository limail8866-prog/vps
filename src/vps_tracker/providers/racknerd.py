from dataclasses import replace

from bs4 import BeautifulSoup

from ..http import requester
from ..models import Plan
from .common import parse_cards, renewal_policy
from .fallback import fetch_from_sources

SOURCE_URL = "https://www.racknerd.com/specials/"


def parse(html: str, source_url: str = SOURCE_URL) -> list[Plan]:
    plans = parse_cards(html, "RackNerd", source_url)
    # 官方 FAQ 明确针对本页所有 VPS specials；只读回答，不从提问推断。
    soup = BeautifulSoup(html, "html.parser")
    for detail in soup.select("#faq details"):
        question = detail.select_one("summary")
        answer = detail.select_one("p")
        if question and answer and "renew" in question.get_text().lower():
            policy = renewal_policy(answer.get_text(" ", strip=True))
            if policy is not None:
                plans = [
                    replace(plan, renewal_same=policy) if plan.renewal_same is None else plan
                    for plan in plans
                ]
                break
    return plans


def fetch() -> list[Plan]:
    return fetch_from_sources("racknerd", parse, requester)
