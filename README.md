# VPS 比价爬虫

Python 3.11 项目，每天抓取 RackNerd 和 CloudCone 的公开套餐，按**人民币月均价**排序，
输出 `reports/YYYY-MM-DD.md` 和 `data/latest.json`。报告日期使用 UTC。

## 安装与运行

推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --frozen --extra dev --python 3.11
uv run --frozen --extra dev python -m vps_tracker run
uv run --frozen --extra dev pytest
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
```

也可以使用 Python 3.11 虚拟环境和 pip：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m vps_tracker run
```

`python cli.py run` 和安装后的 `vps-tracker run` 也可以运行。
`--output-dir /path/to/output` 可以指定输出目录，默认是当前工作目录。

### 网络与失败处理

- 抓取入口：`https://www.racknerd.com/BlackFriday/`、`https://cloudcone.com/vps/`。
- 汇率：`https://open.er-api.com/v6/latest/USD`；首次成功后保存到 `data/fx-cache.json`。
  实时获取失败时使用有效缓存，并在报告显示缓存时间和失败原因。缓存没有硬性过期时间，
  因此旧缓存仅用于参考；不会内置或虚构汇率。
- 使用带项目地址的 User-Agent，连接超时 10 秒、请求超时 20 秒；
  网络故障、429 和 5xx 最多尝试三次，采用退避并处理数字形式的 Retry-After。
  同一商家的请求（包括重试、重定向和子域名）起点至少相隔 2 秒，保持 TLS 校验。
- 单家抓取失败会记录原因并继续其他家。页面无法解析、没有可售套餐也视为失败。
  没有可用汇率时保留原始套餐，但不进行人民币排行。
- 至少一个套餐完成排行时退出码为 0；全部抓取失败或没有套餐可排名时为 1。
  两种情况都会生成报告和 JSON，便于排查。

### 比价规则

人民币月均价 = 原价 × 人民币汇率 ÷ 付款周期月数；年付除以 12，季付除以 3，
半年付除以 6，两年付除以 24，三年付除以 36。非美元币种通过 USD 基准交叉换算。
价格和汇率使用 `Decimal`，JSON 保存为十进制字符串，展示时保留两位小数。

CPU 为核数；内存/磁盘按 1024 MB = 1 GB，流量按 1000 GB = 1 TB。
仅收录能够同时确认价格、币种、付款周期和四项配置的卡片，排除已售罄和划掉的原价。
CloudCone 页面同时显示月均价和实际年付金额时，采用 `Billed ... per year` 的年付金额，
再按 12 个月均摊，避免把广告月均价当作实际月付价格。
未公布续费政策时 `renewal_same` 为 `null`；明确首期优惠或恢复原价的套餐单独标出续费涨价。
当前排行比较公开广告价格，不含税费、附加费用，也不验证订单库存或地区限制。
两个入口的活动和页面可能变化；普通套餐也可能出现，是否促销需结合商家说明核实。

## 添加商家

1. 在 `src/vps_tracker/providers/` 创建模块，实现 `fetch() -> list[Plan]`。
   使用 `vps_tracker.http.requester` 请求页面，复用限速、超时和重试。
2. 将 HTML 解析拆为不联网的 `parse(html)`。可以复用 `common.parse_cards`，
   也可写专用解析器；价格或付款周期不明确时拒绝猜测。
3. 在 `providers/__init__.py` 的 `PROVIDERS` 注册模块的 `fetch` 函数。
4. 保存不含个人信息的 HTML 卡片快照到 `tests/fixtures/`，补充成功、页面变化、
   售罄和续费政策的离线测试。`*-live.html` 是实际公开页面的套餐/FAQ 片段，
   其来源记录在该目录的 README；其他 HTML 是人工固定的边界回归样本。
5. 执行 pytest、ruff，并真实运行一次抓取，检查报告和 JSON。

`Plan` 包含商家、套餐名、配置、原价/币种/周期、续费状态、购买链接和带时区的抓取时间。
任何商家模块抛出的异常都会写入报告，不会中断其他商家。

## 每日自动更新

`.github/workflows/daily.yml` 每天 **UTC 00:00（北京时间 08:00）**运行，也支持手动触发。
安装锁定依赖后先跑离线测试和 lint，再抓取，将报告与 JSON 提交回当前分支。
汇率缓存通过 Actions Cache 跨运行复用，不提交到 Git。
全部抓取失败时仍提交诊断报告，工作流最终标为失败；部分成功时报告列出失败商家。

合并到默认分支后定时任务才会生效。仓库 Actions 设置需允许工作流写入仓库，
默认分支保护也需允许机器人提交；若禁止直接提交，应改为机器人创建更新 PR。
GitHub 定时任务可能延迟执行，长期不活跃的公共仓库可能暂停定时任务。

测试默认禁止真实网络连接，所有 HTTP 测试使用 MockTransport，解析测试读取本地快照。
