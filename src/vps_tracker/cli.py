import argparse
import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .config import Config, decimal_value, load_config, using_config
from .fx import fetch_rates
from .history import update_history
from .models import Plan
from .providers import PROVIDERS
from .providers.fallback import SOURCE_OBSERVATIONS
from .rank import filter_changes, rank_plans, ranking_options, select_plans
from .report import write_report
from .timezone import BEIJING

LOG = logging.getLogger(__name__)


def _run(output_dir: Path, config: Config) -> int:
    failures: dict[str, str] = {}
    plans: list[Plan] = []
    successful: set[str] = set()
    for name, fetch in PROVIDERS.items():
        try:
            fetched = fetch()
            if not fetched:
                raise ValueError("未返回任何可售套餐")
            plans.extend(fetched)
            successful.update(plan.provider for plan in fetched)
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
    stamp = datetime.now(BEIJING)
    sources = SOURCE_OBSERVATIONS.get() or {}
    changes = update_history(output_dir, plans, rates, successful, failures, stamp, sources)
    selected = select_plans(ranked, config.min_ram_gb, config.sort_by, config.max_monthly_cny)
    changes = filter_changes(changes, config)
    report, data = write_report(
        output_dir,
        selected,
        rates,
        failures,
        stamp,
        unranked,
        changes,
        ranking_options(config),
        sources,
    )
    LOG.info(
        "报告：%s；数据：%s；可排名套餐：%d；筛选后：%d", report, data, len(ranked), len(selected)
    )
    return 0 if ranked else 1


def run(output_dir: Path, config: Config | None = None) -> int:
    config = config or load_config()
    select_plans([], config.min_ram_gb, config.sort_by, config.max_monthly_cny)
    with using_config(config):
        token = SOURCE_OBSERVATIONS.set({})
        try:
            return _run(output_dir, config)
        finally:
            SOURCE_OBSERVATIONS.reset(token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VPS 促销套餐每日人民币月均价排行")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="抓取全部商家并生成报告")
    run_parser.add_argument("--output-dir", type=Path, default=Path.cwd())
    show_parser = commands.add_parser("show", help="离线查看、筛选已有报告，不重新抓取")
    show_parser.add_argument("--input", type=Path, default=Path("data/latest.json"))
    for command in (run_parser, show_parser):
        command.add_argument("--config", type=Path, help="默认读取当前目录 config.toml")
        command.add_argument("--min-ram-gb", type=float, help="最低内存 GB，覆盖配置文件")
        command.add_argument("--sort", choices=["monthly_cny", "cny_per_gb"], help="排序方式")
        command.add_argument("--max-monthly-cny", help="人民币月均预算上限（包含边界）")
    alert_parser = commands.add_parser("alerts", help="对最新报告中低于阈值的套餐创建去重 issue")
    alert_parser.add_argument("--config", type=Path)
    alert_parser.add_argument("--input", type=Path, default=Path("data/latest.json"))
    alert_parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config(args.config)
        if args.command == "alerts":
            from .alerts import notify

            return notify(args.input, args.repository, config)
        if args.min_ram_gb is not None:
            config = replace(config, min_ram_gb=args.min_ram_gb)
        if args.sort:
            config = replace(config, sort_by=args.sort)
        if args.max_monthly_cny is not None:
            config = replace(
                config, max_monthly_cny=decimal_value(args.max_monthly_cny, "月均预算上限")
            )
        if args.command == "show":
            from .view import show

            print(show(args.input, config), end="")
            return 0
        return run(args.output_dir.resolve(), config)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
