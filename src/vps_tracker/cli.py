import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from .fx import fetch_rates
from .models import Plan
from .providers import PROVIDERS
from .rank import rank_plans
from .report import write_report

LOG = logging.getLogger(__name__)


def run(output_dir: Path) -> int:
    failures: dict[str, str] = {}
    plans: list[Plan] = []
    for name, fetch in PROVIDERS.items():
        try:
            fetched = fetch()
            if not fetched:
                raise ValueError("未返回任何可售套餐")
            plans.extend(fetched)
            LOG.info("%s：抓取 %d 个套餐", name, len(fetched))
        except Exception as exc:
            failures[name] = f"{type(exc).__name__}: {exc}"
            LOG.error("%s：%s", name, failures[name])
    rates = None
    try:
        rates = fetch_rates(output_dir / "data" / "fx-cache.json")
        if rates.warning:
            LOG.warning(rates.warning)
    except Exception as exc:
        failures["fx"] = f"{type(exc).__name__}: {exc}"
        LOG.error("汇率：%s", failures["fx"])
    ranked, unranked = [], []
    if rates:
        valid = []
        for plan in plans:
            if plan.currency.upper() not in rates.rates:
                unranked.append(plan)
                failures[f"fx/{plan.currency}"] = f"没有 {plan.currency} 汇率，相关套餐未排名"
            else:
                valid.append(plan)
        ranked = rank_plans(valid, rates)
    else:
        unranked = plans
    report, data = write_report(output_dir, ranked, rates, failures, datetime.now(UTC), unranked)
    LOG.info("报告：%s；数据：%s；可排名套餐：%d", report, data, len(ranked))
    return 0 if ranked else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VPS 促销套餐每日人民币月均价排行")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="抓取全部商家并生成报告")
    run_parser.add_argument("--output-dir", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return run(args.output_dir.resolve())
