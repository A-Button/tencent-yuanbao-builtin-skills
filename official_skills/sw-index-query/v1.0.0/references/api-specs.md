# 行情适配与返回约定

行情优先 westock CLI，必要时通过网页检索补充并核实来源、日期和口径。最终回复规则见 [DATA_SOURCE.md](DATA_SOURCE.md)。本页供脚本实现参考，不将内部函数名和执行诊断暴露给普通用户。

| 内部能力 | CLI | 返回与口径 |
|---|---|---|
| 行情 | `westock quote {symbol} --raw` | `price/prev_close/open/high/low/time/amount/volume` |
| K线 | `westock kline {symbols} --period day/week/month --limit N --raw` | `date/last/open/high/low/volume/amount`，按日期升序规范化 |
| 成分 | `westock sector constituent {symbol} --limit 0 --raw` | 成分代码与名称；只有具备真实权重才参与权重分析 |
| 估值 | `westock sector valuation {symbol} --raw` | `EndDate/PeTTM/PbLF/PeTTMPct/PbLFPct` |
| 分时 | `westock minute {symbol} --raw` | 分钟粒度；实际具备的字段才展示 |
| 外部指数K线 | `westock kline {registered_symbol} ... --raw` | 根据登记表定位品种，核验交易日期、币种与单位 |

`801010` 对应 `pt01801010`，只在 `datasource.py` 转换。单代码可返回扁平列表；批量使用 `Data[].Symbol` 定位，不猜测顺序。缺失项有限重试，持续异常留在内部诊断并执行网页补充流程。

网页快照可以补充文字与表格。技术指标和回测必须使用完整且可核实的时间序列，不能由搜索摘要或零散点位补齐。
