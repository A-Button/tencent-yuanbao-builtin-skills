# Fortune Telling（算命 App）

演示 App Skill 设计文档里"UI 直接调用 Script"与"UI 触发 Agent 继续推理"
两条交互路径的示例 App：填写姓名 / 性别 / 出生日期后，用户可以：

- 点 **✨ 测测星座**：纯规则计算，不需要模型推理，走 `app.callScript` 短路。
- 点 **🔮 立即算命**：需要 Agent 结合姓名/性别/生日做开放式推理和话术生成，
  走 `app.sendMessage`，正常进入 react_loop。

## 可用脚本

- `calc_zodiac`：根据出生月日计算星座，参数 `{"birth_date": "1995-05-20"}`
  或 `{"birth_month": 5, "birth_day": 20}`，返回
  `{"zodiac": "金牛座", "emoji": "🐂", "date_range": "4月20日-5月20日", ...}`。

## 触发方式

- 用户对 Agent 说"帮我打开算命 App" → Agent 调
  `load_app(app_skill_name="fortune-telling")` → load_app 下发 UI
  （`STRUCTURED app.resource`，`sessionId="fortune-telling"`），前端渲染表单。
- 点击"✨ 测测星座" → 前端发 `GUI_ACTION(app.callScript)`，
  `action_payload.appSession="fortune-telling"`、`name="calc_zodiac"` →
  agent_server 短路在沙箱执行 `/data/skills/fortune-telling/scripts/calc_zodiac.py`
  并回 `STRUCTURED app.result`，不进入模型推理。
- 点击"🔮 立即算命" → 前端发一条同时带 `TEXT`（自然语言请求）和
  `GUI_ACTION(app.sendMessage)`（`structuredContent` 携带姓名/性别/生日）的消息 →
  `action_type=app.sendMessage` 不在短路范围内，正常进入 pre_process/react_loop，
  由模型结合表单信息生成算命话术。
