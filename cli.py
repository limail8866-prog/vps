"""兼容 python cli.py run；推荐 python -m vps_tracker run。"""

from vps_tracker.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
