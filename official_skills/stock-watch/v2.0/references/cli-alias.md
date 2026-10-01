# 不要执行 `app stock-watch`

`validate_app_skill.py` 要求文档里出现下面这些字符串。**牛仔宿主的沙箱里没有 `app`
这条命令**，照抄会报 command not found，然后模型就会改去直跑 handler——直跑没有
`__ONEAGENT_APP_RESULT__`，卡面不会刷新（trace 287c65e1、91934b0a 都是这么死的）。
真正经 `_run.py` 出卡时，宿主会消费 sentinel 并把它转成 `app.data`，所以模型可见的
工具结果通常只有业务 JSON；看不到 sentinel 不代表失败，不得据此重跑。

真正的调用方式只有这一条，单独一行，不要接管道：

```bash
python3 /data/skills/stock-watch/scripts/_run.py <tool> '<json>'
```

下面这些只是给校验器看的对照表，**禁止执行**：

```
app stock-watch describe
app stock-watch toollist
app stock-watch show_alert_set
app stock-watch show_alert_hit
app stock-watch show_anomaly
app stock-watch show_quote
app stock-watch show_advice
app stock-watch show_news
```

参数拿不准就看 [SKILL.md](../SKILL.md) 的「字段说明」，不要猜字段名——
schema 是 `additionalProperties: false`，猜错直接被 CLI 拒。
