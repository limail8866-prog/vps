import socket
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from vps_tracker.models import Plan


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("测试禁止联网；请使用快照或 MockTransport")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def html():
    return lambda name: (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


@pytest.fixture
def plan():
    base = Plan(
        "Example",
        "Small VPS",
        1,
        1,
        20,
        2,
        Decimal("12"),
        "USD",
        "annually",
        None,
        "https://example.com/order",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    return lambda **kwargs: replace(base, **kwargs)
