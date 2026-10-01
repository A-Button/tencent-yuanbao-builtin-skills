# A2UI 卡片

`--ui-mode a2ui` 生成的 `assets/ui/card.json`。它由**端上的 A2UI 引擎**渲染，不进 iframe，
所以没有 HTML、没有 CSS、也没有页内 JS——能画什么完全取决于 catalog 声明了哪些组件。

全屏工作区仍是普通 H5（`workspace.html`），由卡片里的 `open_workspace` 引过去。两者不嵌套。

在 `app.yaml` 中声明卡片时，URI 必须遵守 [资源 URI 命名](app_yaml.md#资源-uri-命名)：使用 `ai_apps.skills.{skill_name}_{页面名}_res`，默认页也可省略页面名。不要给 A2UI 卡片使用 H5 的 `ui://` URI。

## 文件里放什么

顶层只有 `components` 数组：

```json
{ "components": [ { "id": "root", "component": "Card", "child": "body" } ] }
```

**不要**写 `version`、`surfaceId`、`createSurface`、`updateComponents`、`messages`。宿主会把这个
数组包成完整的 A2UI 消息再喂给引擎；自己写一份只会和宿主的值打架。

> 从 `xcard-page-generator` 那类工具拿到的产物是 `.jsonl`（每行一条完整消息）。取
> `updateComponents.components` 那个数组放进来即可，其余部分丢掉。

## 数据从哪来

卡片是**数据驱动的壳**，本身不带数据。tool 出参会整份挂到数据模型的**根路径**，组件用
JSON Pointer 取：

```
handler return {"books": [...], "count": 2}
卡片里写       {"path": "/count"}、{"path": "/books"}
```

所以绑定路径的起点就是 handler 返回字典的键名；stdout 是模型内容，不参与卡片数据绑定。改 handler 的返回结构，卡片要跟着改。

动态列表用 `children: {path, componentId}`，**列表项内部用相对路径**：

```json
{ "id": "list", "component": "List", "children": { "path": "/books", "componentId": "row" } },
{ "id": "row", "component": "Column", "children": ["row-title"] },
{ "id": "row-title", "component": "Text", "text": { "path": "title" } }
```

`{"id": "list", "component": "List", "path": "/books"}` 这种写法**引擎不会报错，但一行都不会画**。
这类静默失败是 A2UI 最费时间的坑：静态校验通过不等于运行态正确，一定要在工坊调试台里看一眼。

## 协议约束

以下每条错了都不会崩，只会画出一张缺东西的卡片，看起来像样式没写对：

- 必须有 `id: "root"`，引擎从它开始渲染。
- 每个组件都要有非空且唯一的 `id`。
- `child` / `children` 引用的 id 必须存在于同一个数组里。
- 组件名和属性必须来自 catalog（`Card`、`Column`、`Row`、`Text`、`Button`、`List`、`Image`、
  `TextField`、`CheckBox`、`ChoicePicker`、`Tabs`、`Divider`、`Icon`、`Modal`、`Slider`、
  `Video`、`AudioPlayer`、`Visibility`，以及 xCard 扩展的 `Box`、`Clickable`、`IconButton`、
  `ItemPicker`、`PlatformSwitch`、`Stepper`、`Switcher`）。发明属性不会报错，只会被忽略。
- 颜色写 token 名，不写 hex；优先用 `variant`（`h1`~`h4`、`body`、`caption`），`style` 只表达
  variant 表达不了的差异。
- 不要把 CSS 概念搬进来：没有渐变、阴影、transform、绝对定位，`style` 也不是 `styles`。
- `Button` / `Clickable` / `IconButton` 必须有真实 `action`，不要用带背景的 `Text` 假装按钮。

## 转场到全屏

卡片上放一个可点组件，action 用保留名 `open_workspace`：

```json
{
  "id": "expand",
  "component": "Button",
  "child": "expand-label",
  "action": {
    "event": {
      "name": "open_workspace",
      "context": { "resourceUri": "ui://<app-id>/workspace" }
    }
  }
}
```

目标必须在 `app.yaml` 的 `resources[]` 里声明过（`resources` 是 uri → path 的唯一映射表），
且必须是 H5——全屏形态是 H5 的事。`validate_app_skill.py` 会检查这两条。

其余 action（业务事件）端上是当 GUI_ACTION 回传给 agent 的，不会去调 skill 的 tool。

## 怎么验

```bash
python3 <creator>/scripts/validate_app_skill.py <app-dir>
```

它查的是静态结构：组件树完整性、引用闭环、转场目标闭环、顶层是否混入了完整消息。

**真正的验收在创意工坊的调试台**——那里跑的就是端上同一个 A2UI 引擎，选中 tool、填入参、
运行，卡片会用真实出参渲染出来，引擎拒收会直接报出 code 和 path。静态校验替代不了这一步。
