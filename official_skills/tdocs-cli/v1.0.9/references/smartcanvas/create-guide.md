# 智能文档创建指南

仅当用户明确要求「智能文档 / smartcanvas」时使用本指南；普通在线 Word 类文档默认走 `doc`。新建 smartcanvas 时，**优先使用 `smartcanvas create-smartcanvas-by-mdx` 一步创建**；仅在需要指定父目录、空间或后续追加多段内容时，才退化为 `manage create-file` + `smartcanvas edit` 两步流程。

前置：已了解 `cmd-smartcanvas.md` 的核心概念。MDX 规范详见 `mdx-references.md`。

---

## 方式 A（显式要求 smartcanvas 时首选）：一步创建 `smartcanvas create-smartcanvas-by-mdx`

```bash
# 一步创建：标题 + MDX 正文（推荐用 @filepath 读取长文档）
tdocs-cli smartcanvas create-smartcanvas-by-mdx --title "<标题>" --mdx @./body.mdx
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--title` | ✅ | 文档标题 |
| `--mdx` | ✅ | 文档正文，默认 MDX；支持 `@filepath` 从文件读取 |
| `--content-format` |  | `mdx`（默认，推荐）/ `markdown`；传 `markdown` 时按标准 Markdown 解析 |

返回字段含 `file_id`，可用 `--jq '.file_id'` 提取后继续编辑。

---

## 方式 B（兜底）：两步流程 `manage create-file` + `smartcanvas edit`

仅在需要指定 `--parent-id` / `--space-id` 等放置位置参数，或需要分多段写入时使用。

```bash
# 1. 创建空白文档（可指定 parent-id / space-id）
# 不用 --jq，保留完整 JSON 中的 file_id 和 doc_url
tdocs-cli manage create-file --type 8 --title "<标题>"

# 2. 写入 MDX 内容（--action 2 不传 --id 等同写入全文）
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --content @./body.mdx

# 3. 仅当完整响应没有可用链接时补查一次
tdocs-cli manage query-file-info --file-id '<file_id>' --jq '.file | {file_id, name, doc_url}'
```

| 关键参数 | 说明 |
|---|---|
| `manage create-file --type 8` | 智能文档类型固定为 `8` |
| `--title` | 文档标题（必填） |
| `--parent-id` | 可选，目标文件夹 ID |
| `smartcanvas edit --action 2` | INSERT_AFTER，新文档不传 `--id` 即为写入正文 |
| `--content` | MDX 内容，支持 `@filepath` 从文件读取（长文档推荐） |

---

## 内容生成规则

### 1. 模板匹配（优先执行）

在[模板列表](#模板列表)中按 **精确 > 场景 > 分类 > 通用** 优先级匹配。

匹配到模板时：
- 模板文件位于 `references/smartcanvas/templates/`，读取并参考其 frontmatter 与章节结构
- **必须用用户实际内容替换模板示例数据**，禁止原样照搬
- 无匹配则跳过模板，自由生成

### 2. frontmatter 必备

MDX 内容必须以 frontmatter 开头：

```
---
title: 文档标题
icon: 📋
cover: <image_id>
---

正文 ...
```

- `cover` 默认必须设置：检索合适图片 → 上传获取 `image_id` → 填入；仅上传失败才省略。
- `icon` 选用与主题契合的 emoji。

> **已知不稳定（配图/封面降级）**：`manage upload-image` 当前后端不稳定，可能返回 `50000 服务繁忙`（与图片大小/参数无关）。上传图片连续失败时，**不要死磕重试、更不要因此放弃创建文档**：直接省略 `cover` 与正文配图，先把**纯文字版**文档创建出来即可。

### 3. 图片约束（强制）

禁止在任何位置使用 http/https 外链，必须先上传获取 `image_id`：

| 位置 | 写法 |
|---|---|
| 封面 | frontmatter 中 `cover: <image_id>` |
| 正文（MDX） | `<Image src='<image_id>' alt='描述' />` |
| 正文（Markdown） | `![描述](<image_id>)` |

### 4. MDX 规范自检

写入前对照 `mdx-references.md` 检查：

- frontmatter 格式正确
- 仅使用规范中声明的组件
- 颜色使用 token（非 CSS 值）
- 图片全部为 `image_id`
- 缩进为 4 空格，块级组件三段式写法

---

## 示例

### 简单智能文档（纯 Markdown，首选 create-smartcanvas-by-mdx）

```bash
tdocs-cli smartcanvas create-smartcanvas-by-mdx --title "会议纪要" --mdx "---
title: 会议纪要
icon: 📝
---

## 参会人员

张三、李四、王五

## 议题

- Q2 核心 KPI：用户增长 30%
- 下周输出方案初稿"
```

### 带高级组件的智能文档（首选 create-smartcanvas-by-mdx + 文件）

```bash
tdocs-cli smartcanvas create-smartcanvas-by-mdx --title "项目周报" --mdx @./weekly_report.mdx
```

`weekly_report.mdx` 片段：

```mdx
---
title: 项目周报
icon: 📊
---

<Callout icon="📌" blockColor="light_blue" borderColor="blue">
    本周核心进展：完成用户模块重构，性能提升 40%。
</Callout>

## 本周完成

<Todo checked>
    用户模块重构
</Todo>
<Todo>
    文档更新（进行中）
</Todo>
```

### 需要指定父目录时（兜底两步流程）

```bash
tdocs-cli manage create-file --type 8 --title "项目周报" --parent-id <folder-id>
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --content @./weekly_report.mdx
# 若 create-file 完整响应没有可用链接，只补查一次
tdocs-cli manage query-file-info --file-id '<file_id>' --jq '.file | {file_id, name, doc_url}'
```

---

## 模板列表

模板文件位于 `references/smartcanvas/templates/`。

| # | 模板标题 | 适用场景 | 文件名 |
|---|---|---|---|
| 1 | 阶段性工作总结 | 季度/月度工作总结 | `q1_quarterly_marketing_operations_summary.mdx` |
| 2 | 晋升述职报告 | 职级晋升答辩 | `p6_to_p7_promotion_report.mdx` |
| 3 | 实习生实习报告 | 实习总结 | `summer_internship_report_data_analyst.mdx` |
| 4 | 试用期转正总结 | 试用期工作回顾 | `ui_designer_probation_summary.mdx` |
| 5 | 项目复盘报告 | 项目结束后复盘 | `app_2_project_retrospective.mdx` |
| 6 | 品牌宣传方案 | 品牌营销策划 | `new_tea_brand_annual_promotion_plan.mdx` |
| 7 | 产品需求文档 | PRD 编写 | `ecommerce_membership_points_prd.mdx` |
| 8 | 市场营销推广方案 | 促销活动策划 | `online_education_summer_marketing_plan.mdx` |
| 9 | 活动策划方案 | 线下活动策划 | `company_5th_anniversary_event_plan.mdx` |
| 10 | 运营规划方案 | 年度运营规划 | `community_group_buying_annual_operation_plan.mdx` |
| 11 | 商业计划书 | 创业融资 BP | `smart_home_iot_business_plan.mdx` |
| 12 | 个人自媒体运营方案 | 自媒体运营 | `food_review_self_media_operation_plan.mdx` |
| 13 | 副业计划 | 副业规划 | `office_worker_knowledge_side_business_plan.mdx` |
| 14 | 竞品分析报告 | 产品竞品对比 | `short_video_platform_competitive_analysis_2026.mdx` |
| 15 | 行业趋势分析报告 | 行业研究 | `2025_ai_industry_trend_analysis_report.mdx` |
| 16 | 用户调研报告 | 用研报告 | `online_office_tool_user_research_report.mdx` |
| 17 | 市场可行性分析 | 市场调研评估 | `community_fresh_delivery_feasibility_report.mdx` |
| 18 | 产品体验评测报告 | 产品对比评测 | `smartwatch_comparison_apple_watch_vs_huawei_gt.mdx` |
| 19 | 目标人群画像分析 | 用户画像 | `maternity_ecommerce_user_persona_report.mdx` |
| 20 | 选址/选品分析报告 | 商业选址分析 | `coffee_shop_location_analysis_report.mdx` |
| 21 | 商业模式分析报告 | 商业模式研究 | `shared_powerbank_business_model_report.mdx` |
| 22 | 求职自荐信 | 求职应聘 | `internet_product_manager_cover_letter.mdx` |
| 23 | 推荐信 | 学术/职业推荐 | `graduate_admission_recommendation_letter.mdx` |
| 24 | 个人职业规划书 | 职业发展规划 | `finance_graduate_career_plan.mdx` |
| 25 | 面试常见问题准备清单 | 面试准备 | `internet_product_manager_interview_checklist.mdx` |
| 26 | 英文自我介绍 | 外企面试 | `english_self_introduction_for_interview.mdx` |
| 27 | 旅行攻略 | 出行规划 | `quanzhou_3_day_travel_guide.mdx` |
| 28 | 婚礼策划清单 | 婚礼筹备 | `chinese_modern_wedding_planning_guide.mdx` |
| 29 | 生日派对策划清单 | 派对筹备 | `space_theme_6th_birthday_party_plan.mdx` |
| 30 | 家庭年度预算规划 | 家庭财务 | `2026_family_annual_budget_plan.mdx` |
| 31 | 搬家物品整理清单 | 搬家整理 | `shared_apartment_moving_checklist.mdx` |
| 32 | 健身训练计划 | 运动健身 | `12_week_muscle_building_workout_plan.mdx` |
| 33 | 读书笔记 | 阅读总结 | `principles_ray_dalio_book_notes.mdx` |
| 34 | 电影/书籍推荐清单 | 内容推荐 | `career_growth_books_and_movies_recommendations.mdx` |
| 35 | 个人年度目标规划 | 年度目标 | `2026_personal_annual_goal_plan.mdx` |
| 36 | 宠物养护指南 | 宠物饲养 | `british_shorthair_cat_care_guide.mdx` |
| 37 | 家庭食谱/每周菜单 | 饮食规划 | `family_weekly_healthy_meal_plan.mdx` |
| 38 | 节日祝福文案集 | 节日祝福 | `annual_holiday_greeting_messages.mdx` |
