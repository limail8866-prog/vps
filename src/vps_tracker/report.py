from datetime import datetime
from pathlib import Path

from .fx import Rates
from .models import Plan
from .rank import RankedPlan
from .storage import atomic_write, write_json

CYCLE_LABELS = {
    "monthly": "月付",
    "quarterly": "季付",
    "semiannually": "半年付",
    "annually": "年付",
    "biennially": "两年付",
    "triennially": "三年付",
}


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_report(
    ranked: list[RankedPlan],
    rates: Rates | None,
    failures: dict[str, str],
    stamp: datetime,
    unranked: list[Plan],
) -> str:
    lines = [
        f"# VPS 每日排行 — {stamp.date().isoformat()} (UTC)",
        "",
        f"生成时间：{stamp.isoformat()}",
        "",
        "人民币月均价 = 套餐原价 × 对人民币汇率 ÷ 付款周期月数；年付按 12 个月均摊。",
        "仅比较广告价格；税费、附加费用、地区限制和库存以商家结算页为准。",
        "",
    ]
    if rates is not None:
        lines += [
            f"汇率：1 USD = {rates.rates['CNY']} CNY；"
            f"{'缓存' if rates.cached else '实时'}，获取时间 {rates.fetched_at.isoformat()}。",
            "汇率来源：https://open.er-api.com/v6/latest/USD",
            "",
        ]
        if rates.warning:
            lines += [f"> {_escape(rates.warning)}", ""]
    else:
        lines += ["> 无可用汇率，未生成价格排行。", ""]
    lines += [
        "| 排名 | 商家 | 套餐 | CPU | 内存 GB | 磁盘 GB | 流量 TB | 原价 | 月均人民币 | 续费 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(ranked, 1):
        p = row.plan
        renewal = {True: "同价", False: "⚠ 续费涨价", None: "未知（请核实）"}[p.renewal_same]
        # 商家链接可能包含括号；编码它们以保持 Markdown 可点击。
        url = p.url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")
        lines.append(
            f"| {index} | {_escape(p.provider)} | [{_escape(p.name)}]({url}) | {p.cpu} | "
            f"{p.ram_gb:g} | {p.disk_gb:g} | {p.bandwidth_tb:g} | "
            f"{p.price} {p.currency}/{CYCLE_LABELS[p.billing_cycle]} | "
            f"¥{row.monthly_cny:.2f} | {renewal} |"
        )
    if not ranked:
        lines += ["", "本次没有可排名的套餐。"]
    increases = [row for row in ranked if row.plan.renewal_same is False]
    if increases:
        lines += ["", "## 续费涨价提醒", ""]
        lines += [
            f"- {_escape(row.plan.provider)} / {_escape(row.plan.name)}："
            "促销价仅适用于首期，续费金额请查看商家结算页。"
            for row in increases
        ]
    if unranked:
        lines += ["", "## 未参与排名", ""]
        lines += [
            f"- {_escape(p.provider)} / {_escape(p.name)}：{p.price} {p.currency}，缺少可用汇率。"
            for p in unranked
        ]
    lines += ["", "## 抓取状态", ""]
    if failures:
        lines += [f"- **{_escape(name)}**：{_escape(reason)}" for name, reason in failures.items()]
    else:
        lines += ["所有商家抓取成功。"]
    lines += ["", "续费未知的套餐不会默认视为续费同价。", ""]
    return "\n".join(lines)


def write_report(
    root: Path,
    ranked: list[RankedPlan],
    rates: Rates | None,
    failures: dict[str, str],
    stamp: datetime,
    unranked: list[Plan] | None = None,
) -> tuple[Path, Path]:
    unranked = unranked or []
    report_path = root / "reports" / f"{stamp.date().isoformat()}.md"
    data_path = root / "data" / "latest.json"
    atomic_write(report_path, render_report(ranked, rates, failures, stamp, unranked))
    write_json(
        data_path,
        {
            "generated_at": stamp.isoformat(),
            "timezone": "UTC",
            "fx": rates.to_dict() if rates else None,
            "plans": [row.to_dict() for row in ranked],
            "unranked_plans": [plan.to_dict() for plan in unranked],
            "failures": failures,
        },
    )
    return report_path, data_path
