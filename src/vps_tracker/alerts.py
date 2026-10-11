import hashlib
import json
import logging
import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx

from .config import Config
from .history import plan_id
from .http import USER_AGENT
from .timezone import BEIJING

LOG = logging.getLogger(__name__)


def create_alerts(payload: dict, repository: str, threshold: Decimal, client: httpx.Client) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("仓库必须为 owner/repository")
    if not threshold.is_finite() or threshold <= 0:
        raise ValueError("阈值必须为有限正数")
    generated = datetime.fromisoformat(payload["generated_at"])
    if (
        generated.tzinfo is None
        or generated.astimezone(BEIJING).date() != datetime.now(BEIJING).date()
    ):
        raise ValueError("拒绝使用过期报告发送提醒，请先运行 run")
    candidates = []
    for row in payload["plans"]:
        amount = Decimal(row["monthly_cny"])
        if not amount.is_finite() or amount <= 0:
            raise ValueError("报告中的月均价无效")
        if amount < threshold:
            candidates.append(row)
    if not candidates:
        LOG.info("没有低于 %s 元/月的套餐", threshold)
        return 0
    existing = set()
    endpoint = f"/repos/{repository}/issues"
    page = 1
    while True:
        response = client.get(endpoint, params={"state": "all", "per_page": 100, "page": page})
        response.raise_for_status()
        issues = response.json()
        for issue in issues:
            if "pull_request" not in issue:
                existing.update(
                    re.findall(r"<!-- vps-alert:([a-f0-9]+) -->", issue.get("body") or "")
                )
        if len(issues) < 100:
            break
        page += 1
    created = 0
    for row in candidates:
        identity = f"{plan_id(row)}|{threshold.normalize()}"
        marker = hashlib.sha256(identity.encode()).hexdigest()[:24]
        if marker in existing:
            continue
        amount = Decimal(row["monthly_cny"])
        renewal = {True: "同价", False: "首期促销，续费涨价", None: "以官方说明为准"}[
            row["renewal_same"]
        ]
        body = (
            f"月均价 **¥{amount:.2f}**，低于提醒阈值 ¥{threshold}/月。\n\n"
            f"原价：{row['price']} {row['currency']}，付款周期：{row['billing_cycle']}。\n\n"
            f"配置：{row['cpu']} CPU / {row['ram_gb']} GB RAM / {row['disk_gb']} GB 磁盘。\n\n"
            f"续费：{renewal}。{row.get('renewal_note') or ''}\n\n"
            f"购买链接：{row['url']}\n\n生成时间：{payload['generated_at']}\n\n"
            "仅为价格提醒，库存、税费和地区限制以商家结算页为准。\n\n"
            f"<!-- vps-alert:{marker} -->"
        )
        # 不自动重试 POST；即使响应丢失，下一次先查 marker 也能避免重复 issue。
        response = client.post(
            endpoint,
            json={
                "title": f"VPS 低价提醒：{row['provider']} / {row['name']} — ¥{amount:.2f}/月",
                "body": body,
            },
        )
        response.raise_for_status()
        existing.add(marker)
        created += 1
        LOG.info("已创建提醒：%s", response.json().get("html_url", ""))
    return created


def notify(path: Path, repository: str, config: Config) -> int:
    if not config.alerts_enabled:
        LOG.info("issue 提醒未启用")
        return 0
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("issue 提醒需要 GH_TOKEN；GitHub Actions 自动使用 github.token")
    payload = json.loads(path.read_text(encoding="utf-8"))
    with httpx.Client(
        base_url="https://api.github.com",
        timeout=20,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    ) as client:
        create_alerts(payload, repository, config.alert_threshold_cny, client)
    return 0
