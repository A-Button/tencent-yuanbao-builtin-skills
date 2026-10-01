# 人格测试与已有结果

- 开始测试：直接交付 20 题 `quick`；只有明确要求深度、详细、完整或 50 题时使用 `deep`。不先问量表、主题或出生资料，不在聊天中逐题作答。
- 已有四字母或连续分数：直接解释，不强迫重测。
- 人格知识：直接回答，不启动测试。明确结合已有 MBTI 与星座时读 [zodiac-personality.md](zodiac-personality.md)，顺带提到星座不改变测试流程。

用户明确要求官方 MBTI 且宿主无正式授权集成时，说明本测试是基于 IPIP 连续特质的非官方四字母近似。

## 开始测试

```bash
python3 scripts/artifact_pipeline.py personality --version quick
```

流水线构建并校验，把页面写到宿主能收取的位置，并返回 `delivery` 与填好路径的 `media_info`。脚本失败或 `delivery.ok` 为 false 时不要改流水线、不要自己搬文件。**`delivery.ok` 为 true 时必须交付**：把 `media_info` 贴进回复草稿，再运行返回的 `verify_command`，通过后发出；正文里简短说明打开作答、完成后复制结果回对话。

```
<media_info>[{"type": "file", "description": "人格测评页，打开即可作答", "path": "<output 绝对路径>"}]</media_info>
```

深度版仅将 `quick` 改为 `deep`。不要重复调用独立构建器或校验器，不增加模型生成。

## 解释已有结果

用户粘贴 `PERSONALITY_RESULT_V1`，或同时含 `axes` 与 `big_five_mean_1_to_5` 的 JSON，直接把它作为人格结果输入，不调用后端计分器。校验四轴和五项 1—5 均值完整、字母与比例一致；字段矛盾、缺失或四轴均为 X 且五项都在中点时，不补猜类型，邀请重新复制或重测。只有四字母时明确证据较少，不补造比例。

生成解释时读 [chart-language.md](chart-language.md) 和 [safety.md](safety.md)。先概括最明显的连续维度差异，再用工作、学习或相处场景解释；四字母只作导航。不反推逐题答案、真实经历或固定身份。没有关注点时先给简短综合解读，不追问；校准与后续入口保持可跳过。

## 按需资料

计分、量表来源或许可疑问才读 [ipip-assessments.md](ipip-assessments.md)。修改页面或诊断交互／交付才读 [html-skill-architecture.md](html-skill-architecture.md)；维护元宝或类型场景正文时分别读 [personality-mascots.md](personality-mascots.md)、[personality-profiles.md](personality-profiles.md)。正常构建不加载这些资料。
