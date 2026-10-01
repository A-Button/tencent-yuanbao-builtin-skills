# 新版人格报告内容

仅在维护或诊断页面时读取；正常生成仍走 artifact_pipeline。

内容表为 `scripts/mbti_report_profiles.json`，完整覆盖16型，每型包含 summary、core、strengths、watch、communication、decision、work、team、relationship、growth、reflection。使用倾向表达，不推断现实履历，不展示代表人物或职业预测。

报告采用最新设计基线的结构：人格概括→四轴→左侧性格长卡与右侧沟通／决策双卡→三个场景便签→成长建议／自我观察→复制与高清海报。

完整类型只读取对应档案。平分显示维度报告与回看相关题目的入口，不拼接虚构类型档案；全同作答只显示质量提示及原始均值。

报告内容、图像与显示标签不进入复制数据；`PERSONALITY_RESULT_V1` 仍只包含四轴连续值与大五原始均值。
