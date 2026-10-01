---
name: yuanbao-intro-xcard-demo
description: 生成「元宝自我介绍」XCard 卡片（A2UI v1.0 Basic Inline Surface），或以此为起点改写出新的介绍卡。适用于“元宝介绍卡片”“XCard demo 卡片”“做一张 A2UI 介绍卡”；不用于带自定义组件、token overlay 或渲染器扩展的页面。
metadata:
  version: v1.0.0
  gallery-index: '001'
version: v1.0.0
---

# 元宝介绍 XCard Demo

一张可直接投放到 XCard Gallery 的「元宝自我介绍」卡片，作为 Basic Inline Surface 的最小可跑样例。新卡片可以从它复制后改写，而不是从空白 JSONL 起步。

## 产物

`gallery/001_yuanbao-intro.jsonl`：三行分段消息，只使用 basic catalog。

| 行 | 消息 | 作用 |
| --- | --- | --- |
| 1 | `createSurface` | 声明 `surfaceId: yuanbao-intro` 与 basic catalog |
| 2 | `updateComponents` | 完整组件树，文案全部走 DataModel 绑定 |
| 3 | `updateDataModel` | 卡片文案数据 |

结构：`root` → `hero`（头像 + 名称 + 副标题）→ `Divider` → 小节标题 → 5 条能力（`Row` = emoji + 文案）→ 页脚说明。

## 改写流程

1. 复制 `gallery/001_yuanbao-intro.jsonl` 为新文件，`surfaceId` 改为表达新业务语义的 kebab-case。
2. 改第 2 行的组件树：先定 `root` 与容器关系，再改叶子组件，所有 child 引用保持可解析。
3. 改第 3 行的 DataModel，让绑定路径与组件一致；删除数据时显式传 `null`。
4. 改完立即做静态校验（见下），再交付。

需要重复实例化的结构时，把布局抽成 `templates/<template-id>/<semver>.json`，目录名与 `templateId` 用同一个 kebab-case，绑定改为相对路径；Gallery JSONL 仍发送展开后的完整组件集合。当前 demo 是一次性卡片，不需要模板化。

## 硬约束

- 只用 basic catalog 的组件、属性和 `variant`；组件名、属性、枚举不能凭记忆扩充。
- 每个组件必须有非空 `id`，最终状态必须有 `id: "root"`。
- 一行一个完整 JSON object，顺序为 `createSurface` → `updateComponents` → `updateDataModel`，同一 `surfaceId`。
- `updateDataModel.value` 必须存在。
- 不写 `style`：默认样式由 `variant` 与设计 token 决定；`style` 里只能写 token 名，不能写 raw hex、阴影、绝对定位或 CSS 属性。
- 文案与数据走 DataModel 绑定，不把业务文案写死在组件里；绑定的层级分隔符是 `/`。
- 需要按钮时用 `Button` 并配真实 action，不要用带背景的 `Text` 伪造。
- 远程图片才用 `Image`，且必须是可访问 URL 并提供 `description`；本 demo 的头像与能力图标用 emoji 文本，避免不可访问的资源。

## 交付前校验

用 XCard 页面生成技能自带的校验器跑一遍，报错修到通过再交付：

```bash
python3 scripts/validate_xcard_bundle.py /absolute/path/to/001_yuanbao-intro.jsonl
```

校验器需要 `basic_catalog`、`xcard_catalog`、`tokens` 资源；资源缺失时先配置 XCard 资源包路径，不要跳过校验直接交付。

落到 Gallery 运行时，按目标平台的清单登记样例：`sampleId` 与 `surfaceId` 一致，`messageCount` 等于 JSONL 非空行数（本文件为 3）。
