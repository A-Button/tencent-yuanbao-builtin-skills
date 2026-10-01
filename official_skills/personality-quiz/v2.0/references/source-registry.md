# 按需出处核验

普通概念、盘面解释和问卷解读通常不加载书目。用户要求原文、具体出处、版本对照，或当前判断确实取决于有争议的规则时，才查对应体系资料：

| 体系 | 来源表 |
|---|---|
| 八字 / 子平法 | [sources-bazi.md](sources-bazi.md) |
| 西洋占星 | [sources-western.md](sources-western.md) |
| 紫微斗数或印度占星 | [sources-imported.md](sources-imported.md) |
| 人格测试 | [sources-personality.md](sources-personality.md) |
| 塔罗 | [sources-tarot.md](sources-tarot.md) |

书目表只是检索线索，不是对当前判断的论证。`seeded` 是待核对资料；`reviewed-scope` 只确认适用范围；`reviewed-rule` 才表示具体规则核对；`reviewed-card-draft` / `reviewed-case-draft` 仍是团队内容草稿。日常解释不需要先遍历这些状态。

## 原文与出处

- 只有实际核对的文字才作逐字引文；给出能支持该句的具体出处。无法核对时用转述或说明不确定，不补造书名、版本、页码，也不以模型“记得”代替核验。
- 区分原典、注解、译文、团队摘要与用户材料；不因有出处就把传统解释写成个人事实或经验证预测。引文只取必要部分，遵守来源许可与宿主引用限制。
- 输出格式服从当前产物契约。普通聊天可以附核验链接；现有深度报告 `paragraphs[].text` 只接受单段纯文本，不支持引用卡片、脚注或 Markdown 链接。需要可点击出处时在报告外单独给出；不得擅自扩展 Schema、把链接塞进正文或改写生成的 HTML。既有页面规定保留在内部的来源与许可信息，仍按其资产契约处理。

维护资料只保存必要书目信息、短摘要、已核验规则及版本／章节、冲突与复核状态，不导入来源不明全文或凭模型记忆生成的引文。
