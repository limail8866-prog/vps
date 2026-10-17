from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .fx import Rates
from .models import Plan
from .rank import RankedPlan
from .storage import atomic_write, write_json
from .timezone import BEIJING

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
    changes: dict | None = None,
    ranking_options: dict | None = None,
    sources: dict | None = None,
) -> str:
    stamp = stamp.astimezone(BEIJING)
    lines = [
        f"# VPS 每日排行 — {stamp.date().isoformat()}（北京时间）",
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
            f"{'缓存' if rates.cached else '实时'}，"
            f"获取时间 {rates.fetched_at.astimezone(BEIJING).isoformat()}。",
            "汇率来源：https://open.er-api.com/v6/latest/USD",
            "",
        ]
        if rates.warning:
            lines += [f"> {_escape(rates.warning)}", ""]
    else:
        lines += ["> 无可用汇率，未生成价格排行。", ""]
    if ranking_options:
        sort_label = (
            "人民币月均价" if ranking_options["sort_by"] == "monthly_cny" else "每 GB 内存月均价"
        )
        budget = ranking_options.get("max_monthly_cny")
        budget_label = f"；月均价 ≤ ¥{budget}" if budget is not None else ""
        lines += [
            f"筛选：内存 ≥ {ranking_options['min_ram_gb']:g} GB{budget_label}；"
            f"排序：{sort_label}。",
            "",
        ]
    lines += [
        "| 排名 | 商家 | 套餐 | CPU | 内存 GB | 磁盘 GB | 流量 TB | 原价 | "
        "月均人民币 | 每 GB 内存 | 续费 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(ranked, 1):
        p = row.plan
        renewal = {True: "同价", False: "⚠ 续费涨价", None: "未知（请核实）"}[p.renewal_same]
        if p.renewal_note:
            if p.renewal_same is None:
                renewal = "按官方续费规则"
            renewal += f"；{_escape(p.renewal_note)}"
        bandwidth = "不限量" if p.bandwidth_tb is None else f"{p.bandwidth_tb:g}"
        # 商家链接可能包含括号；编码它们以保持 Markdown 可点击。
        url = p.url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")
        lines.append(
            f"| {index} | {_escape(p.provider)} | [{_escape(p.name)}]({url}) | {p.cpu} | "
            f"{p.ram_gb:g} | {p.disk_gb:g} | {bandwidth} | "
            f"{p.price} {p.currency}/{CYCLE_LABELS[p.billing_cycle]} | "
            f"¥{row.monthly_cny:.2f} | ¥{row.cny_per_gb:.2f}/月 | {renewal} |"
        )
    if not ranked:
        empty = (
            "筛选后没有匹配的套餐。"
            if ranking_options
            and (
                ranking_options["min_ram_gb"] > 0
                or ranking_options.get("max_monthly_cny") is not None
            )
            else "本次没有可排名的套餐。"
        )
        lines += ["", empty]
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
    if changes is not None:
        lines += ["", "## 套餐变化", ""]
        if changes["baseline_date"]:
            lines += [
                f"与 {changes['baseline_date']}（北京时间）比较；商家原币种月均价变化才计为涨跌。",
                "",
            ]
            labels = {
                "new": "🆕 新上架",
                "removed": "下架",
                "price_drop": "📉 降价",
                "price_increase": "涨价",
            }
            for event in changes["events"]:
                row = event["plan"]
                detail = ""
                if "previous" in event:
                    before = event["previous"]
                    detail = (
                        f"：{before['price']} {before['currency']}/"
                        f"{CYCLE_LABELS[before['billing_cycle']]}"
                        f" → {row['price']} {row['currency']}/{CYCLE_LABELS[row['billing_cycle']]}"
                        f"（{Decimal(event['change_percent']):+.2f}%）"
                    )
                lines += [
                    f"- {labels[event['kind']]}：{_escape(row['provider'])} / "
                    f"{_escape(row['name'])}{detail}"
                ]
            if not changes["events"]:
                lines += ["已成功抓取的商家在当前筛选范围内暂无套餐变化。"]
        else:
            lines += ["尚无前一天的有效快照，本次仅建立历史基线，不推断新上架或下架。"]
        if changes["skipped_providers"]:
            lines += [
                "库存观测不完整（抓取失败或来源切换），暂停下架判断并保留最后库存："
                + "、".join(changes["skipped_providers"])
                + "。"
            ]
        lines += [f"> 历史数据提示：{_escape(warning)}" for warning in changes["warnings"]]
    policies = {
        (p.plan.provider, p.plan.renewal_note, p.plan.renewal_url)
        for p in ranked
        if p.plan.renewal_url
    }
    if policies:
        lines += ["", "## 续费规则来源", ""]
        lines += [
            f"- {provider}：{note or '官方续费说明'} — {url}"
            for provider, note, url in sorted(policies)
        ]
    if sources:
        lines += ["", "## 抓取来源", ""]
        for name, observation in sources.items():
            if observation["selected_url"]:
                lines += [f"- {name}：{observation['selected_url']}"]
            lines += [
                f"  - 已回退：{item['url']} — {_escape(item['reason'])}"
                for item in observation["failures"]
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
    changes: dict | None = None,
    ranking_options: dict | None = None,
    sources: dict | None = None,
) -> tuple[Path, Path]:
    stamp = stamp.astimezone(BEIJING)
    unranked = unranked or []
    report_path = root / "reports" / f"{stamp.date().isoformat()}.md"
    data_path = root / "data" / "latest.json"
    atomic_write(
        report_path,
        render_report(ranked, rates, failures, stamp, unranked, changes, ranking_options, sources),
    )
    write_json(
        data_path,
        {
            "generated_at": stamp.isoformat(),
            "timezone": "Asia/Shanghai",
            "fx": rates.to_dict(
                {row.plan.currency for row in ranked} | {p.currency for p in unranked}
            )
            if rates
            else None,
            "plans": [row.to_dict() for row in ranked],
            "unranked_plans": [plan.to_dict() for plan in unranked],
            "failures": failures,
            "changes": changes,
            "ranking": ranking_options,
            "sources": sources,
        },
    )
    return report_path, data_path
