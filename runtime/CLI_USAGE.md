# 沙盒平台 CLI 使用手册

本文档说明沙盒中五个命令行工具的用法，全部为可执行二进制（或脚本），位于 `/usr/local/bin/`。
其中 `yuanbao-cli`、`westock`、`tdocs-cli`、`magika` 可直接在沙盒终端执行；`app` 是技能调用框架，
通常由运行时自动调用，也可手动调用。

---

## 一、yuanbao-cli — 元宝 CLI（资源下载）

**二进制**：`/usr/local/bin/yuanbao-cli`（10.1 MiB，ELF 动态链接、已 strip）

### 用法

```
yuanbao-cli download --skill <skill> <path> --output-dir <dir> [--output <filename>]
yuanbao-cli ppt download <template-path> --output-dir <dir> [--output <filename>]
yuanbao-cli -v
```

### 子命令

| 命令 | 说明 |
|---|---|
| `download` | 下载技能资源到输出目录。从服务端下载并**缓存到临时目录**。 |
| `ppt download` | 下载 PPT 模板（等同 `download --skill pptx`）。 |
| `-v` | 输出版本号。 |

### 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--skill <skill>` | 是 | 技能名（如 `pptx`） |
| `<path>` | 是 | 资源路径 |
| `--output-dir <dir>` | 是 | 输出目录 |
| `--output <filename>` | 否 | 指定输出文件名 |

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `YUANBAO_API_BASE` | `https://yuanbao.test.hunyuan.woa.com` | 服务端地址（**注意：是 `.test.` 测试域名**） |
| `YUANBAO_ROUTE_ENV` | — | 路由环境 |
| `YUANBAO_API_KEY` | — | Bearer Token（可选） |

### 示例

```bash
# 下载某个技能资源到 /data/workspace/out/
yuanbao-cli download --skill pptx "templates/business_plan.pptx" \
    --output-dir /data/workspace/out --output my_template.pptx

# 等价写法：通过 ppt 子命令下载 PPT 模板
yuanbao-cli ppt download "templates/business_plan.pptx" --output-dir /data/workspace/out
```

> 注：`YUANBAO_API_BASE` 默认指向 `*.test.hunyuan.woa.com`，说明这是**内部测试环境**的端点。
> 若在沙盒外使用，需自行配置 `YUANBAO_API_BASE` 指向可用服务。

---

## 二、westock — 金融数据与智能选股

**二进制**：`/usr/local/bin/westock`（2.6 MiB，ELF 静态链接、无节区头，逆向难度高）

### 用法

```
westock [command] [subcommand] [flags]
westock [command] --help
```

### 命令分类

#### 金融数据

**行情**
- `kline` — K 线数据（个股、指数、板块、ETF、外汇、期货、可转债）
- `minute` — 分时数据（个股、指数、板块、外汇、期货、可转债）
- `quote` — 实时行情（支持指定历史日期）

**技术分析**
- `chip` — 筹码成本分析（仅 A 股）
- `technical` — 技术指标

**市场**
- `changedist` — 沪深 A 股涨跌分布
- `connect` — 陆股通成份股清单
- `ipo` — 新股日历
- `lhb` — 全市场龙虎榜
- `market-overview` — A 股市场总览
- `trade-calendar` — A 股交易日历

**指数**
- `index list` — 指数清单
- `index constituent` — 指数成份股

**板块**
- `sector constituent` — 板块成份股
- `sector finance` — 申万行业财务指标
- `sector forecast` — 申万行业盈利预测
- `sector info` — 板块信息与区间交易
- `sector oper` — 申万行业经营数据
- `sector ranking` — 全市场板块行情榜
- `sector valuation` — 板块估值

**发现**
- `hot stock` — 热搜股票
- `hot etf` — 热搜 ETF
- `hot sector` — 热门板块
- `hot news` — 热文榜
- `search` — 统一搜索入口

**财务**
- `disclosure` — 财报披露日历（A 股/港股/美股，又称业绩预约披露日）
- `finance` — 财务数据（三大表）

**资金**
- `fund flow` — 个股资金流向
- `fund block` — 大宗交易
- `fund lhb` — 个股龙虎榜
- `fund margin` — 融资融券
- `fund north-holding` — 北向资金持仓
- `fund short` — 卖空数据
- `fund south-holding` — 南下资金持仓

**简况**
- `buyback` — 公司回购（A 股/港股）
- `dividend` — 分红数据（A 股/港股/美股）
- `profile` — 股票简况
- `shareholder` — 股东研究（A 股/港股）

**ETF**
- `etf overview` — ETF 概览
- `etf profile` — ETF 档案
- `etf holdings` — 持仓
- `etf nav` — 净值历史

**研究**
- `consensus` — 一致预期（A 股、港股）
- `dehydrated` — 脱水研报
- `esg` — ESG 评级（中证/聚源）
- `rating` — 机构评级（港股、美股）
- `report list` — 研报列表
- `report detail` — 研报详情
- `score` — 股票评分（最新及周/月/季变动）

**资讯**
- `news list` — 新闻列表
- `news detail` — 资讯详情
- `notice list` — 公告列表
- `notice detail` — 公告原文

**事件**
- `calendar` — 投资日历（个股事件日历）
- `events` — 个股事件总览（42 类事件标签）
- `risk` — 风险事件监控（仅 A 股）
- `suspension` — 停复牌列表

**宏观**
- `macro indicator` — 宏观指标查询
- `macro list` — 宏观指标目录
- `macro expect` — 海外预期日历
- `macro expect list` — 预期地区代码

**期货 / 外汇 / 债券**
- `futures detail` — 期货合约资料（外盘商品/金融期货 + 港股股指期货）
- `forex list` — 外汇品种列表（离岸人民币/主要货币对/美元指数）
- `bond` — 可转债/可交换债详情（发行/评级/期限利率/转股/赎回回售/条款/利率变动/现金流明细）

#### 智能选股

- `screen condition` — 条件选股
- `screen event` — 事件选股
- `screen label` — 标签选股 / 选基
- `screen ranking` — 统一排行选股 / 选基
- `screen strategy` — 策略选股

### 全局标志

| 标志 | 说明 |
|---|---|
| `-h, --help` | 显示帮助 |
| `-v, --version` | 显示版本 |

### 示例

```bash
# 查贵州茅台（600519）的实时行情
westock quote 600519

# 查沪深A股涨跌分布
westock changedist

# 查热搜股票榜
westock hot stock

# 查板块行情榜
westock sector ranking

# 条件选股
westock screen condition '<条件 JSON>'

# 查某股的资金流向
westock fund flow 600519
```

> 注：多数子命令需进一步传参（如股票代码、查询条件 JSON）。用 `westock <command> --help`
> 查看该子命令的具体参数说明。

---

## 三、tdocs-cli — 腾讯在线文档 CLI

**二进制**：`/usr/local/bin/tdocs-cli`（10.1 MiB，ELF 动态链接、已 strip）

### 用法

```
tdocs-cli <service> <command> [flags]
tdocs-cli <service> --help
```

### 服务（Service）清单

| 服务 | 说明 |
|---|---|
| `sheet` | 计算、筛选、统计、Excel 操作 |
| `manage` | 文件管理（重命名/移动/删除/复制/上传/权限等） |
| `smartcanvas` | 报告、笔记、文章、总结等 |
| `smartsheet` | 结构化数据管理 |
| `doc` | 论文、公文、合同等专业 Word 档编辑 |
| `mind` | 层次化知识整理（思维导图） |
| `flowchart` | 流程架构展示（流程图） |
| `space` | 空间管理（创建空间/查询列表、节点） |
| `collaboration` | 企业共享空间成员与创建管理 |
| `ocr` | 图片识别（提取文字/转为 Word、Excel） |
| `slide` | 幻灯片 PPT 编辑 |
| `workflow` | 多步工作流命令 |

### 各服务核心子命令

#### `manage` — 文件管理（40+ 个子命令）

`ai-search-file`、`apply-download`、`apply-upload`、`batch-import-file-to-saas`、
`batch-link-file-to-saas`、`batch-query-permission`、`check-skill-update`、
`complete-upload`、`consume-login-code`、`copy-file`、`create-file`、`create-login-code`、
`delete-file`、`get-content`、`get-file-privilege`、`get-privilege`、`get-user-info`、
`import-file-to-saas`、`init-upload`、`license`、`list-file`、`move-file`、
`pwd-free-login`、`query-batch-saas-import-progress`、`query-file-info`、
`query-saas-import-progress`、`query-task`、`rename-file-title`、
`resolve-third-file-id`、`scrape-progress`、`scrape-url`、`search-file`、
`set-file-privilege`、`set-privilege`、`upload-image`、`verify-license`，
以及 `report-unsupported-feature`（功能不支持时上报）。

#### `doc` — Word 文档编辑（部分，完整列表见 `tdocs-cli doc --help`）

文档结构类：`resolve-document-structure`、`get-outline`、`get-last-operable-pos`

文本类：`insert-text`、`insert-paragraph`、`insert-paragraph-with-text`、
`insert-markdown`、`insert-html-content`、`find`、`find-and-replace`

富文本类：`insert-image`、`insert-code-block`、`insert-math`、
`insert-normal-link`、`insert-numbering`、`insert-task`、`insert-word-art`

表格类：`insert-table`、`insert-cols`、`insert-rows`、`get-table-info`、`delete-table`

批注与修订：`insert-comment`、`get-comments`、`accept-all-revisions`

对比：`compare-documents`（段落级差异）

创建：`create-with-markdown`、`create-doc-with-html`

#### 其他服务

`slide`、`sheet`、`flowchart`、`mind`、`smartcanvas`、`smartsheet` 的子命令
请分别用 `tdocs-cli <service> --help` 查看。

### 示例

```bash
# 查看 doc 服务全部子命令
tdocs-cli doc --help

# 查看 manage 服务全部子命令
tdocs-cli manage --help

# 查看空间管理子命令
tdocs-cli space --help

# 创建/编辑文档需先通过 manage 获取文件信息或创建文件
tdocs-cli manage create-file '<JSON 参数>'
```

> 提示：文档类编辑命令（如 `doc` 下的插入操作）大多要求先用
> `resolve-document-structure` 获取文档结构以定位正确的位置索引，
> 再执行插入。这是 tdocs-cli 的标准工作流。

---

## 四、magika — AI 文件类型识别

**二进制**：`/usr/local/bin/magika`（31 MiB，Mozilla 出品的文件类型识别工具）

### 用法

```
magika [OPTIONS] [PATH]...
```

### 参数

| 参数 | 说明 |
|---|---|
| `[PATH]...` | 要分析的文件路径列表。用 `-` 从标准输入读取（仅可用一次） |

### 选项

| 选项 | 说明 |
|---|---|
| `-r, --recursive` | 递归识别目录内文件 |
| `--no-dereference` | 识别符号链接本身而非跟随其内容 |
| `--colors` / `--no-colors` | 强制开/关彩色输出 |
| `-s, --output-score` | 额外输出预测置信度分数 |
| `-i, --mime-type` | 输出 MIME 类型而非描述 |
| `-l, --label` | 输出简短标签 |
| `--json` | JSON 格式输出 |
| `--jsonl` | JSONL 格式输出 |
| `--format <CUSTOM>` | 自定义输出格式，支持占位符： |
| | `%p` 文件路径 `%l` 标签 `%d` 描述 `%g` 分组 |
| | `%m` MIME 类型 `%e` 可能扩展名 `%s` 分数 `%S` 分数百分比 |
| | `%b` 被覆盖时的模型输出 `%%` 字面 % |
| `-h, --help` | 帮助摘要 |
| `-V, --version` | 版本号 |

### 示例

```bash
# 识别单个文件
magika /data/workspace/unknown_file

# 批量识别目录内所有文件
magika -r /data/workspace/

# 输出 MIME 类型 + 置信度分数
magika -i -s unknown_file

# JSON 格式输出（便于脚本处理）
magika --json unknown_file

# 自定义格式：路径 + 标签 + 分数百分比
magika --format '%p %l (%S)' unknown_file
```

---

## 五、app — 技能调用框架

**脚本**：`/usr/local/bin/app`（25 KiB，Python 脚本，UTF-8，可直接读源码）

### 用法

```
app <skill> toollist | describe | <tool> '<json>'
```

### 子命令

| 命令 | 说明 |
|---|---|
| `toollist` | 列出指定技能的所有工具 |
| `describe` | 描述技能/工具的详细信息 |
| `<tool> '<json>'` | 调用指定工具，参数为 JSON 字符串 |

### 环境变量

| 变量 | 说明 |
|---|---|
| `ONEAGENT_APP_CALLER` | 调用方标识，取值 `model`（模型）或 `app`（应用） |
| `tool_visibility` | 工具可见性：`model` / `app` / 两者 |

### 工作机制

`app` 读取技能目录下的 `app.yaml`（定义 tools/resources），进行 schema 校验后路由调用。
支持两种 handler：

- **`script`**：执行脚本，stdout 为完整业务 JSON
- **`python`**：调用同名同步函数（独立 worker）

stdout 输出有 **30000 字符预算**：超出时把完整信封落盘到 `/data/workspace/.app_result/`，
stdout 只回预览 + 文件路径。

### 示例

```bash
# 列出 travel_plan 技能的所有工具
app travel_plan toollist

# 描述某个工具
app travel_plan describe '<工具名>'

# 调用工具（参数为 JSON）
app travel_plan render_trip '{"trip_id":"abc123"}'
```

> `app` 通常由运行时（nexus-runtime）自动调用，一般不直接手动使用。
> 若要研究实现，可直接读 `/usr/local/bin/app` 源码（已归档于
> `runtime_components.tar.zst` 的 `platform_cli/app`）。

---

## 附录：工具速查

| 工具 | 主要用途 | 是否可直接用 |
|---|---|---|
| `yuanbao-cli` | 下载技能/PPT 模板资源 | ✅ 沙盒内可直接执行 |
| `westock` | 金融数据查询、智能选股 | ✅ 沙盒内可直接执行 |
| `tdocs-cli` | 腾讯在线文档全套操作 | ✅ 沙盒内可直接执行 |
| `magika` | AI 识别文件真实类型 | ✅ 沙盒内可直接执行 |
| `app` | 技能调用框架 | 通常由运行时自动调用 |

### 通用排错

- **连接失败**：检查环境变量（`YUANBAO_API_BASE` 等）是否指向可用服务端点。
- **认证失败**：确认是否有有效的 Token / 登录态（`tdocs-cli` 涉及 `manage pwd-free-login`、
  `consume-login-code` 等登录流程）。
- **参数不明**：所有工具均支持 `<command> --help` 查看该子命令的详细参数。
- **沙盒网络**：注意出站流量走 ZeroProxy MITM 代理（CA 证书见 `ca_certs/zeroproxy-ca.crt`）。
