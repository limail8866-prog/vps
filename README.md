# VPS 比价爬虫

Python 3.11 项目，每天抓取 RackNerd、CloudCone、DediRock、BuyVM 的公开套餐，按**人民币月均价**排序，
输出 `reports/YYYY-MM-DD.md`、`data/latest.json` 和 `data/history/YYYY-MM-DD.json`。
报告标题、文件日期和生成时间使用北京时间（Asia/Shanghai）。

## 不安装也能查看

打开 [每日中文报告](https://github.com/limail8866-prog/vps/tree/main/reports)，
选择最新日期的 Markdown 文件即可看到排行、价格变化和抓取状态。
[Actions](https://github.com/limail8866-prog/vps/actions/workflows/daily.yml) 可以查看执行结果，
也可以点击 **Run workflow** 手动更新。计划每天北京时间 08:00 运行，GitHub 可能延迟调度。
低于 20 元/月的套餐会在 [Issues](https://github.com/limail8866-prog/vps/issues) 提醒。

## 安装与运行

首次使用先下载仓库并进入目录：

```bash
git clone https://github.com/limail8866-prog/vps.git
cd vps
```

已有仓库可先用 `git pull --ff-only` 更新。推荐使用 [uv](https://docs.astral.sh/uv/)：

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

```bash
# 只看内存至少 2 GB 的套餐，按每 GB 内存月均价排序
python -m vps_tracker run --min-ram-gb 2 --sort cny_per_gb
# 只看内存至少 2 GB、月均不超过 20 元的套餐
python -m vps_tracker run --min-ram-gb 2 --max-monthly-cny 20
# 使用自定义配置
python -m vps_tracker run --config ./config.toml
```

`config.toml` 保存来源列表、排序/筛选规则和 issue 提醒阈值。命令行筛选覆盖配置文件。
未指定配置路径时自动读取当前目录的 `config.toml`；目录中没有配置文件时采用内置来源，
提醒默认关闭。显式指定不存在的文件会报错，避免忽略配置。
预算可在 `[ranking]` 设置 `max_monthly_cny = "20"`，省略则不限制；采用精确金额比较，
**包含等于预算的套餐**，区别于低价提醒的严格小于阈值。筛选影响排行、变化列表和提醒候选，
不会删掉每日完整库存。缺少汇率的套餐仍显示在未参与排名中，无法判断是否符合人民币预算。
配置项拼写、类型和数值会在联网前校验；`enabled` 必须写 `true` / `false`，不能加引号。

### 离线查看和筛选

已有 `data/latest.json` 时，无需重新抓取就可以查看保存的排行：

```bash
uv run --frozen python -m vps_tracker show
uv run --frozen python -m vps_tracker show --min-ram-gb 2 --max-monthly-cny 20
uv run --frozen python -m vps_tracker show --sort cny_per_gb
# 读取其他目录的 latest.json，并保存这次筛选结果
uv run --frozen python -m vps_tracker show --input /path/to/data/latest.json > selected.md
```

`show` 本身不联网、不创建 issue、不改写报告或历史，保留原始生成时间和汇率；
首次用 uv 启动仍需安装依赖。`show` 与 `run` 共用配置和命令行筛选参数。
如果保存的 `latest.json` 已经经过筛选，`show` 只能缩小其中的范围；需要扩大范围时，
调整配置后重新执行 `run`。快照损坏或路径错误会返回错误提示。

### 网络与失败处理

- 每家商家的 `sources` 是有顺序的地址列表。RackNerd 优先读取常驻 `/specials/`，
  再尝试 `/NewYear/`、`/BlackFriday/`；请求失败、没有套餐或解析失败都会回退到下一来源。
  最先成功的来源供本次使用，全部失败时报告汇总各来源的失败原因。
- CloudCone 使用 `/vps/`，DediRock 使用首页和两个地区的 VPS 页面，
  BuyVM 使用 KVM Slices 页面及其公开 `/assets/js/plans.js` 库存映射。
  BuyVM 只收录明确未禁用的地区；其“不限量”流量以 `bandwidth_tb: null` 表示。
  DediRock 从动画计数器 `data-to-value` 读取实际金额，排除初始 `0` 和划掉的原价，
  同时排除独立服务器产品。不会执行第三方 JavaScript。
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
`data/latest.json` 只保留 USD 基准、CNY 和参与排行套餐使用的币种汇率。
完整汇率仅保存在不提交 Git 的 `data/fx-cache.json`。

CPU 为核数；内存/磁盘按 1024 MB = 1 GB，流量按 1000 GB = 1 TB。
仅收录能够同时确认价格、币种、付款周期和四项配置的卡片，排除已售罄和划掉的原价。
CloudCone 页面同时显示月均价和实际年付金额时，采用 `Billed ... per year` 的年付金额，
再按 12 个月均摊，避免把广告月均价当作实际月付价格。
未公布续费政策时 `renewal_same` 为 `null`；明确首期优惠或恢复原价的套餐单独标出续费涨价。
CloudCone 的官方条款说明：按原周期自动续费，但商家可以提前 45 天通知调整费用。
因此不冒称“续费同价”，报告显示具体规则和来源链接；`renewal_same` 保持 `null`，
并附 `renewal_note`、`renewal_url`。续费条款读取失败不会让套餐抓取失败。
当前排行比较公开广告价格，不含税费、附加费用，也不验证订单库存或地区限制。
来源的活动和页面可能变化；普通套餐也可能出现，是否促销需结合商家说明核实。

### 套餐变化和每日库存

每日 JSON 历史保存完整库存，筛选只影响报告和 `latest.json`，不会造成虚假下架。
与北京时间前一天的库存对比，标出降价、涨价、新上架和下架；首次运行或没有前一天
有效快照时建立基线，不伪造变化。一天多次运行仍与昨天比较。

套餐使用商家与规范化购买地址作为标识，忽略 utm、ref、aff 和 BuyVM/CloudCone 的展示 token。
价格涨跌按同一币种下的原价/月数判断，单独的汇率变化不会误报商家降价。
抓取失败的商家不判断下架，历史库存保留其最后一次成功观测值，恢复后再比较。
来源回退到另一张页面时，也不把旧来源中的套餐直接当作下架；只有同一来源再次成功
抓取，才确认该来源不再列出的旧套餐。报告记录实际使用的来源及失败回退原因。
报告可能因此与最近一次观测对比，而不是把缺失观测当作下架。

### 低价 issue 提醒

默认配置为严格低于 **20 元/月**。每日工作流调用独立的 `alerts` 子命令，
查询已有 issue（包括已关闭 issue）后，才为未提醒过的套餐创建新 issue。
同一套餐和阈值使用稳定标记去重，不会每天重复创建，也不会因为关闭 issue 再次刷屏。
`run` 本身不会创建 issue；提醒只使用当天最新报告中筛选后的可排名套餐。

```bash
# 需要 GH_TOKEN 或 GITHUB_TOKEN；不要把凭据写入配置文件
python -m vps_tracker alerts --repository limail8866-prog/vps
```

GitHub Actions 使用内置 `github.token`，不需要额外个人 token；工作流声明 `issues: write`。
如需手机推送，请在 GitHub 中关注该仓库的 Issues，并启用 GitHub App 的通知。
提醒只代表价格达到阈值，不保证促销库存；也不会自动下单。

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
至少一个套餐完成排行时发送低价 issue 提醒，历史 JSON 同时提交回仓库。

合并到默认分支后定时任务才会生效。仓库 Actions 设置需允许工作流写入仓库，
默认分支保护也需允许机器人提交；若禁止直接提交，应改为机器人创建更新 PR。
GitHub 定时任务可能延迟执行，长期不活跃的公共仓库可能暂停定时任务。

测试默认禁止真实网络连接，所有 HTTP 测试使用 MockTransport，解析测试读取本地快照。
