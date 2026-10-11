from ..http import requester
from ..models import Plan
from .common import parse_cards

SOURCE_URL = "https://cloudcone.com/vps/"


def parse(html: str) -> list[Plan]:
    return parse_cards(html, "CloudCone", SOURCE_URL)


def fetch() -> list[Plan]:
    return parse(requester.get(SOURCE_URL).text)
