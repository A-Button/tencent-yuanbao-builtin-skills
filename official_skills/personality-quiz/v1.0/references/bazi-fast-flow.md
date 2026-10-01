# 八字入口兼容说明

八字、西占与组合盘现共用 [chart-flow.md](chart-flow.md) 的简短请求入口 `chart_quick.py`。旧 `bazi_quick_chart.py` 命令保留兼容，默认仍为八字，不需要迁移已有调用数据。

时辰范围的计算细节归于 [chart-contract.md](chart-contract.md#时辰范围实现与维护)，仅在维护或诊断计算时读取。
