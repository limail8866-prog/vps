from dataclasses import replace

from bs4 import BeautifulSoup

from ..http import requester
from ..models import Plan
from .common import parse_cards, renewal_policy

SOURCE_URL = "https://www.racknerd.com/BlackFriday/"


def parse(html: str) -> list[Plan]:
    plans = parse_cards(html, "RackNerd", SOURCE_URL)
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
    return parse(requester.get(SOURCE_URL).text)
