---
name: pptx
description: "处理所有与 .pptx 相关的任务：创建演示文稿、编辑现有幻灯片、读取或提取内容、按模板生成、合并或拆分文件，以及处理版式、备注和评论。只要用户提到 deck、slides、presentation，或出现任何 .pptx 文件名（无论后续用于编辑、分析、总结或转写），都应使用此技能。"
---

# PPT 技能

从模板生成 PPT。skill 路径用环境变量 `$YB_SKILL_PATH`（未设置时默认 `/data/skills`；镜像内即 `/data/skills`），脚本一律 `python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/xxx.py` 调用，无需 `cd`。
模板**按需下载**：先 `grep` `${YB_SKILL_PATH:-/data/skills}/pptx/templates.txt` 选一条完整 `path`，再用 `yuanbao-cli download` 取到 `$RUN/template.pptx`。`yuanbao-cli` 由平台**预装**、内置路由——只要 `path` 以类别（`商业/学校/政府/设计`）开头就能取到模板，模型无需知道任何地址。模板**只读**，绝不原地改。
每个任务在**当前工作目录**下建独立目录 `RUN="$(pwd)/ppt_runs/<run_id>"`（**不得建在 skill 目录下**；`<run_id>` 任务开始生成一次、全程复用），全程读写它。

**`$RUN` 里的角色**
- `deck*.json` / `content_lines.tsv` / `images.json` / `charts.json` / `tables.json` / `layout_ops.json` / `notes.json` / `*_report.json`：小状态文件，任务全程唯一事实来源，保留到交付。
- `$RUN/unpacked`：`prepare_deck.py` 解包的 OOXML 树，编辑期工作数据（`replace_text`/`replace_image`/`adjust_shape`/`edit_chart`/`edit_table` 都原地改这里），**不是交付物**；`ok:true` 后 `finalize_run.py` 自动清空。
- `$RUN/final.pptx`：唯一交付物，`ok:true` 后才生成。

## 硬规则

- **不用 `python-pptx`，不写临时 `apply_*.py`**：读取/确认页数/排查/修改一律用本技能脚本、`finalize_report.json`、`text_extract.json` 或 OOXML/zip 结构。
- **模板是画布**：按需删页、复制好用版式多次使用、自由重排，不必用满全部页。
- **模板示例内容必须全部本地化，否则阻断交付**：
  - 标题/正文（`texts` 里 `kind:title|body`）原样保留 → `verify_content` 报 `untouched_template_text`。每个 title/body 的 `ref` 必须 `replace` 或 `clear`；`keep` **只允许**用于品牌名/页码等装饰。
  - 图表（`chart_slots`）示例数据 → `check_charts` 报 `untouched_template_chart`：用 `edit_chart` 改写。
  - 表格（`table_slots`）示例内容 → `check_tables` 报 `untouched_template_table`：用 `edit_table` 改写。
- **视觉槽只替换、不新增**（没有槽就不配图）。生图前先看该槽字段（`prepare_deck`/`inspect_deck` 已算好）：
  - `replaceable:true`（无文字压顶、占画布 2%~50% 的独立图位）：**必须**用 `image_generation` 按主题各生成一张不同的图替换；留模板原图 → `untouched_template_image` 阻断。
  - `protected_backdrop:true`（文字压在图上，或图 ≥50% 画布）与 `protected_small_visual:true`（<2%，icon/装饰）：**禁止替换、保留原图**，不为其生图。`replace_image.py` 会拒绝写入，质检分别报 `replaced_protected_backdrop`/`replaced_protected_small_visual`。误换了用 `python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/replace_image.py restore <unpacked> --slide N --visual-index K` 撤回。
- **交付门**：`verify_content`/`check_layout`/`validate_pptx`/`check_images`/`check_charts`/`check_tables`/语义自检 的 blocking 必须全为 0（`apply_plan` 已串好）。`check_contrast` **只是 advisory，不阻断**——"给文字当背景的图默认不换"就是可读性第一防线，别为对比度反复调字色/重生图。

## 效率纪律（轮次有限）

- `load_skill` 只调一次；**不要 `read`/`grep`/`cat` `scripts/*.py`**——读源码是头号轮次黑洞。遇 blocking 只看 headline 和对应 `*_report.json`。
- `apply_plan` 输出**直接读 JSON headline**，不要再写 python 解析 stdout。
- 检索克制：`web_search`/`picture_search` 全程合计 ≤ 3~4 次，先写骨架再按需补数据/图。
- **不中途重开 run**：`--template`、选页 `--slides` 各只调一次。中途 blocking 只改状态文件重跑 `apply_plan`。
- **`--scope` 用物理 slide 编号**（与 `slideN:shapeM` 的 N 一致），不是 `order`；抄 `prepare_deck` 末尾的 `scope速查`。

### 少回合三条（硬约束，替代「每批约 3 页写一点查一点」）

> 事实：`--scope` **只缩反馈范围**，文本/图/表每次仍是**全量应用**累计文件。因此「先写全 → 再少次校验」与「边写边查」结果等价，但回合少得多。

1. **一次成稿**：选页后**一次性**写完整副 `content_lines.tsv`（+`charts.json`/`tables.json`），覆盖 `deck.selected.json` 里每一页每个 title/body 的 ref。**禁止**「写 3 页→自查→再想下 3 页」式滚动写作。
2. **配图一次并行铺满**：所有 `replaceable:true` 槽**同轮并行**生成、一次写满 `images.json`；每槽 ≤1 张；protected 槽不生成。**禁止**按批挤图。
3. **校准一批 + 大组校验（少次 `apply_plan`）**：
   - ≤约 6 页：一条 `apply_plan --lines --images --charts --tables`（不带 `--no-finalize`）到位。
   - >6 页：先对**前约 3 页**跑 1 次 `--no-finalize --scope`（校准系统性写法：ref/数字位/成对框）；修好后把同样写法扫过其余页；再按 **5~8 页一组**做 1~2 次分组校验；最后 `--finalize-only`。
   - **同 scope 最多修 2 轮**：同一 `--scope` 连续两次 `ok:false` 且 blocking 不降 → **立刻改策略**（核对 ref / 缩短文案 / 进下一组），**禁止**第三次原样重跑同一 scope。校准批 2 轮仍有系统性问题就全局扫一遍文案再进分组，别在前 3 页空转。
   - **目标**：12~18 页 deck 的 `apply_plan` 调用 ≤ 4~5 次（1 校准 + 1~2 分组 + 1 finalize + ≤1 修复）。超过就优先 `--finalize-only` 出片。

## 工作流（一次成稿 → 校准 → 分组校验 → 收尾）

⓪ 环境确认 → ① 规划 → ② 选模板(grep templates.txt→yuanbao-cli 下载)/选页 → ③ 一次写全内容 + 一次并行铺满配图 → 校准批 → 大组校验 → ④ 打包。
文本和配图**必须同一次 `apply_plan` 一起传**（先跑纯文本会触发 `image_blocking`）。

0. **环境确认**（每任务开头一次，依赖就绪时毫秒级返回）：`python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/ensure_deps.py -q`。就绪继续；失败按提示排查依赖再继续。
1. **规划**：想清每页讲什么、用什么版式、要不要图，可写 `$RUN/outline.md`。**"要不要图"由内容/主题决定**（讲概念/场景/产品/氛围的页配图；数据清单/引用/目录/联系方式页不配），先有判断再挑带槽的页——顺序不能反。强表达优先 `visual_slots` 足的页，数据汇报优先 `chart_slots`/`table_slots` 足的页。**结构完整**：除超短副本外应含封面、目录（≥8 页且条目与章节一致）、分节过渡页、结尾页；`structure_advisory` 不阻断。
2. **选模板/选页**：`grep` `${YB_SKILL_PATH:-/data/skills}/pptx/templates.txt` 挑一条完整 `path` → `yuanbao-cli download --skill pptx "<path>" --output-dir "$RUN" --output template.pptx` → `prepare_deck.py "$RUN" --template "$RUN/template.pptx"`（打开后按 `best_use`/`visuals`/`charts`/`tables`/`text_density` 核对是否匹配）→ `prepare_deck.py "$RUN" --slides ...` 一次定结构，生成 `deck.selected.json`。详见「选模板」。
3. **一次成稿 + 校准 + 分组校验**（落实上面三条）：
   - 一次写完整副 `$RUN/content_lines.tsv`（每行 `ref<TAB>replace|clear|keep<TAB>文本`）；图表/表格一次写完。漏写 title/body → `unhandled_template_text`。
   - 一次并行铺满 `$RUN/images.json`（所有 `replaceable:true`）。
   - **校准批**（前约 3 页）：
     `python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/apply_plan.py "$RUN" --template "$RUN/template.pptx" --lines content_lines.tsv --images images.json --charts charts.json --tables tables.json --no-finalize --scope <前约3页物理slide号>`
     有系统性问题在此修好，并同步校正其余页。
   - **分组校验**：校准通过后，其余页按 **5~8 页一组**跑 `--no-finalize --scope`，只修报告点名的 ref。`contrast_issues_advisory` 不计入 `ok`。
4. **收尾交付（最高优先级）**：写 `$RUN/notes.json`（口播式、简短）后：
   `python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/apply_plan.py "$RUN" --template "$RUN/template.pptx" --finalize-only --notes notes.json`
   `ok:true` → 交付 `$RUN/final.pptx`；`ok:false` → 看 `finalize_report.json`，只修点名页，重跑该 scope 再 `--finalize-only`。
   > **备注不能拖累出片**：预算紧就直接 `--finalize-only`（不带 `--notes`）。没有备注的成品也远胜于没有成品。

> **两位数 blocking**：按 ~5-8 页/组逐组修到 `ok:true` 再收尾，别用一个巨大 JSON 硬糊。
>
> **量力而行**：宁可 12~18 页做扎实，别铺到 30 页做不完；成稿+校准后尽快 `--finalize-only`。**出片永远优先于页数。**

## 选模板：grep templates.txt 比风格 → yuanbao-cli 下载

模板库按 `类别/场景/风格.pptx` 三层组织。合法 `path` 全部列在 `${YB_SKILL_PATH:-/data/skills}/pptx/templates.txt`（每行一条完整 `path`）。下面是**类别/场景**总览（仅到场景层，具体风格文件名去 `templates.txt` grep）：

- **商业/**：产品方案介绍 | 全员大会、年会 | 品牌升级、活动招商 | 商务合作提案 | 投资路演 Pitch Deck | 新品发布会 | 行业研究报告 | 财报、业务数据 | 述职、月报、季报 | 项目立项、复盘
- **学校/**：K12教师课件 | 博士开题、中期、盲审 | 学术会议、学术报告 | 本科、硕士答辩 | 社团、学生会活动 | 课程作业、小组汇报 | 高校讲座、公开课
- **政府/**：事业单位汇报（公检法、医院、高校行政） | 党建汇报、主题党日 | 国企工作总结 | 政府工作报告 | 政府重要会议简报 | 红色教育、党史学习 | 部门、个人述职
- **设计/**：TED风格演讲 | 作品集（设计、摄影、插画） | 极客、科技、AI主题 | 知识沉淀、自媒体图文（杂志风） | 艺术、文化主题讲座 | 通用展示（国际主义风）

先按需求（主题/受众/场景/风格/页数）定「类别/场景」，再从需求推导关键词用 `grep` 逐步收窄，从结果里凭风格文件名挑一条，记下**完整 `path`**；grep 为空就去掉一层放宽，或 `cat` 该场景下所有条目。**不要**自己拼风格名——合法 `path` 只存在于 `templates.txt`。选定后用 `yuanbao-cli download` 取到 `$RUN/template.pptx`（cli 预装、内置路由，`path` 以类别开头即可，不走本地库、不需地址）。

```bash
# A. grep templates.txt 比风格，挑一条完整 path（多条件逐步收窄）
grep "行业研究报告" "${YB_SKILL_PATH:-/data/skills}/pptx/templates.txt" | grep "科技\|深"
# 例：科技深色 → grep "行业研究报告" ...|grep "科技\|AI"|grep "黑\|深"；旅游活泼 → grep "产品方案介绍" ...|grep "人文\|旅"|grep "明媚\|彩"
# 结果为空去掉一层放宽；仍不够就 grep 整个场景名看全部候选
# B. 下载选中模板到 $RUN（<path> 即 templates.txt 里的整行）
mkdir -p "$RUN" && yuanbao-cli download --skill pptx "<path>" --output-dir "$RUN" --output template.pptx
# C. 打开模板看全部页结构（决定保留/复制哪些页）
python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/prepare_deck.py "$RUN" --template "$RUN/template.pptx"
# D. 选页/复制/重排定结构（输出稳定 ref，写 deck.selected.json）
python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/prepare_deck.py "$RUN" --slides 1,3,5,8
```

**选页策略**：只留相关页，其余删；好版式可复制多次（`--slides 1,4,4,4,7` 复制 slide4 三份各自独立编辑）；页数由需求定，不必凑满模板。

## 内容写作规范

文案写进 `$RUN/content_lines.tsv`，每行 `ref<TAB>replace|clear|keep<TAB>文本`，同框多段用 `||`。`ref` 复制 `deck.selected.json` 的，别猜页码/shape。看每个 ref 的 `kind`/`text`/`bounds`/`autofit` 判断它是什么位。

- **短**：标题 ≤约14字，要点 ≤约24字；别把长句塞进标题框。`kind:title` 只放短标题/标签，正文/多行要点放 `kind:body`。
- **数字/短标签位只放短数据**（模板原文是 `117`/`60%`/`21万亩` 这类）：配套标签也短（"种植面积""同比+12%"）。**严禁把整句/长叙述塞进数字位**——会炸框，被 `data_slot_misuse`（`verify_content`）和严重 `text_overflow`（`check_layout`）阻断。长叙述放 `kind:body`。
- **切题 + 真实数据**：每个 ref 填与本页主题一致的内容、数据与标签对应；用真实数值，不留 `N/A`/`待补充`/`TODO`；图表数据一并改写。
- **成对框同步改**：带 `pair_hint` 的中/英译文框要一起改（或都 `clear`），别只改一个。
- **排版**：分段用 `||`，同段软换行写真实换行、按断句换、避头尾；不写带圈序号①②③；高亮只标核心词/数字；同类框沿用模板字号别忽大忽小，偏移不居中用 `adjust_shape` 的 `anchor:"ctr"`；词间别乱插斜杠。
- **版式有节奏**：图文/左右/数据页交错，避免连续多页同版式。
- **角标/页脚**：`inspect_deck` 的 `master_layout_texts` 是写死在母版/版式的角标；要改直接编辑对应 `ppt/slideLayouts/*.xml` 或 `slideMasters/*.xml` 的 `<a:t>`（只改文字不动结构）。
- 不要把"联系我们/地址/电话"页改成密集内容页。

```
slide5:shape3	replace	2026年中国新能源汽车出海战略
slide5:shape9	replace	要点一||要点二||要点三
slide9:shape5	clear
```

## 配图（必做，和文案一起在 apply_plan 里传）

模板照片/背景是**占位库存图**，`replaceable:true` 的必须换成主题新图。**先由内容定要不要图，再找承载它的槽**——走到本步若某页 `visual_slots` 空，只应是"规划就判定这页不需要图"；若发现该配图的页没槽，是第②步漏配，回去换一张带槽的同类页，别就地放弃。

1. **找槽**：从 `deck.selected.json` 每页 `visual_slots` 取 `ref`（如 `slide5:visual1`；旧模板 `image_slots` 的 `slide5:image1` 也可）。**用重排后的 ref，别用原模板页号。**
2. **只对 `replaceable:true` 逐个生成**：每槽调一次 `image_generation-generate`（`dst_intent:"Text2Image"`，prompt 写清画面+风格、贴近槽的横竖比），**每槽一张不同的图**，绝不复用；可并行。`protected_backdrop`/`protected_small_visual` 一律跳过。
3. **写 `$RUN/images.json`**：`image` 填生成的 http(s) URL（自动下载）或本地路径。随 `apply_plan --images` 传，本步不单独跑命令。

```json
[
  {"ref":"slide5:visual1","image":"https://.../gen1.png"},
  {"ref":"slide23:image1","image":"https://.../gen2.png"}
]
```

- 自动按图位纵横比居中 cover 裁剪；图位有旋转/镜像会自动反向预处理使照片显示为正。替换写入独立媒体、只动该位（复制自同页的多页也互不覆盖）。
- headline `images_failed>0` → 多半 ref 用错（要用重排后的 `slideN:visualK`），改 images.json 重跑。
- `check_images` 阻断：`untouched_template_image`（该换没换）/`replaced_protected_backdrop`/`replaced_protected_small_visual`（后两类用 `replace_image.py restore` 撤回）/`template_logo_wall`（同页 ≥3 张仍是原图，删页或换主题图）；`no_visual`（≥6 页零图零表）是 warning。

## 图表 / 表格（必做，和文案一起传）

**图表**：从 `chart_slots` 取 `ref`（`slide5:chart1`）和当前 `type`/`categories`/`series`，写 `$RUN/charts.json` 用真实数据改写（点数与类目对齐；占比按模板量纲如 `0~1`；系列数与模板一致最稳；可选 `title`）。只改缓存数据，不动样式。随 `--charts` 传。留模板数据 → `check_charts` 报 `untouched_template_chart`。

```json
[
  {"ref":"slide5:chart1","categories":["2021","2022","2023","2024"],
   "series":[{"name":"营收(亿元)","values":[12,18,27,41]},{"name":"毛利(亿元)","values":[3,5,9,15]}],"title":"近四年营收与毛利"},
  {"ref":"slide8:chart1","categories":["华东","华南","华北"],"values":[0.45,0.33,0.22]}
]
```

**表格**：从 `table_slots` 取 `ref`（`slide8:table1`）和 `rows`/`cols`/`cells`，写 `$RUN/tables.json`，`cells` 二维数组按行×列（含表头）逐格填真实内容，某格 `null` 保留原样。只改单元格文本，保留样式。随 `--tables` 传。留模板内容 → `check_tables` 报 `untouched_template_table`。

```json
[
  {"ref":"slide8:table1","cells":[
    ["车型类别","2023销量(万辆)","2024销量(万辆)","2025销量(万辆)"],
    ["纯电动(BEV)","668","771","1013"],
    ["合计","949","1287","1649"]
  ]}
]
```

图表/表格 `ref` 都用重排后的 `slideN:chartK`/`slideN:tableK`。无图表/表格的副本天然通过。

## 演讲备注（收尾前一步，锦上添花不阻断）

站在演讲者视角为**每一页**（含封面/目录/过渡/结尾）写 2~4 句**口播稿**——"这页要点+怎么讲+和上下页的衔接"，不是复述幻灯片文字。数据页点出关键数字的含义；问题页讲归因并给积极信号；举措页说重点讲哪两条。简短、一次写完，别反复打磨。写进 `$RUN/notes.json`（`slide` 是物理编号），收尾随 `--finalize-only --notes notes.json` 注入（缺 notesSlide 的页自动补建，失败不阻断）。

```json
[
  {"slide":1,"note":"开场：各位好，今天汇报上半年经营情况，整体判断稳中有增、承压前行，分四部分展开。"},
  {"slide":9,"note":"最关键的一页：利润率6.8%、同比降1.5个点。讲清三点归因后强调一个积极信号——二季度已企稳回升。"}
]
```

## 应用与交付：apply_plan 三种用法

`apply_plan.py` 串好 plan_from_lines → replace_text → 图片 → 图表 → 表格 →（finalize：verify_content + check_layout + validate_pptx + check_images + check_charts + check_tables + check_contrast[advisory] + 打包）。**文本/图片/图表/表格同一次传**（`--lines --images --charts --tables`），不要分开，也**不要单独调 dry-run/replace_text/verify_content/check_layout/finalize_run**。

1. **批次自查 `--no-finalize --scope <页号>`**：只对 scope 页跑 verify+layout 回传反馈，不打包。headline：`ok`/`scope`/`verify_blocking`/`layout_blocking`/`verify_issues`/`layout_issues`/`contrast_issues_advisory`/`applied`/`images_ok`/`images_failed`。
   ```bash
   python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/apply_plan.py "$RUN" --template "$RUN/template.pptx" --lines content_lines.tsv --images images.json --no-finalize --scope 4,5,6
   ```
2. **收尾打包 `--finalize-only`**：只整副打包+硬关卡，写 `final.pptx`。打包前写 `$RUN/content_semantic.json`（语义自检：未解决占位/事实待补/交付风险，无则空 `issues`）；随 `--notes` 注入备注。
   ```bash
   python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/apply_plan.py "$RUN" --template "$RUN/template.pptx" --finalize-only --notes notes.json
   ```
3. **一步到位（小副本 ≤6 页）**：不带开关，应用+finalize 一次跑完；需版式微调加 `--layout layout_ops.json`。
   ```bash
   python ${YB_SKILL_PATH:-/data/skills}/pptx/scripts/apply_plan.py "$RUN" --template "$RUN/template.pptx" --lines content_lines.tsv --images images.json --charts charts.json --tables tables.json
   ```

finalize headline：`ok`/`final_pptx`/`verify_blocking`/`layout_blocking`/`validate_blocking`/`image_blocking`/`chart_blocking`/`table_blocking`/`contrast_advisory`/`content_semantic_blocking`/`structure_advisory`/… `contrast_advisory`/`structure_advisory` 不阻断。
- `ok:false` → 看 `finalize_report.json`，**优先只改 `content_lines.tsv`**（缩短/改 clear/补文案）重跑受影响页 `--no-finalize --scope` 再 `--finalize-only`。
- `image_blocking` → `images_report.json` 列的图位各生成主题图补进 images.json；`chart_blocking`/`table_blocking` → 改 `charts.json`/`tables.json`；`content_semantic_blocking` → 改 `content_semantic.json` 里未解决内容；`validate_blocking`（极少见，结构损坏）→ 通常重跑 `prepare_deck`→重新应用，别手改 XML。
- 文本替换报错（exit≠0）→ headline 带 errors，只修对应 ref 行重跑。

```json
{"issues":[]}
```
```json
{"issues":[{"severity":"blocking","type":"unresolved_content","detail":"第12页仍有未解决的数据承诺，应改为已核实数据或删除"}]}
```

## 版式微调（可选）

> **写入阶段已自动缩字防溢出**：`replace_text` 写入每框后按框反解，放不下就把该框所有 run 字号成比例改小、并把 `spAutoFit` 转 `normAutofit`（跨 PowerPoint/WPS/LibreOffice 一致；短标签/数字位强制单行）。报告体现为 `autofit_shrunk`。故多数溢出无需手动处理；关闭用 `--no-autofit`。仍以"文案本就写合身"为先。

文案已合适但仍溢出/`check_layout` 报 `overflow`/`overlap` 时，写 `$RUN/layout_ops.json` 随 apply_plan 跑（`--layout layout_ops.json`）。每项一个 ref：
- 自动缩字适配固定框：`{"ref":"slide5:shape3","autofit":"normal"}`（可加 `"fontScale":90`）。
- 移动/缩放（EMU，914400=1英寸；增量 `dx/dy/dcx/dcy`，绝对 `x/y/cx/cy`）：`{"ref":"slide7:shape2","box":{"dy":-180000,"dcy":360000}}`。
- 改字色：`{"ref":"slide5:shape3","fontColor":"FFFFFF"}`（深底白字/浅底深字）。
- 垂直对齐：`{"ref":"slide5:shape3","anchor":"ctr"}`（`ctr`/`t`/`b`）。

版式微调失败不阻断交付。

## 修复预算

按 headline 迭代，**同一 scope / 每次 finalize 最多 2 轮**（以 `content_lines.tsv` 为主），超预算就停并报告 blocking，不写新脚本、不用 `python-pptx`。2 轮内 blocking 不降反平 → 多半 ref 用错页，回 `deck.selected.json` 核对 ref，**禁止**第 3、4 轮原样重跑。两位数 blocking → 按 ~5-8 页组拆开处理，或直接 `--finalize-only` 拿可交付版再定点修。
`check_layout` 的 `text_overflow`：轻度超框是 warning；远超框高（≥约1.2 倍、非模板原生、非 normAutofit）升级 blocking，需缩短文案/改 clear/`autofit`/扩框。基线降级只对"未被替换且未加重"的模板原生溢出生效。`data_slot_misuse` 是 blocking；`circled_number/stray_slash/invalid_data/literal_escape` 是 warning。
排版/配色细则见 [design.md](design.md)（按需读）。

---

## 边界说明

`finalize_run.py` 的四项校验（`verify_content`/`check_layout`/`validate_pptx`/`check_images`）是 **rollout 硬关卡**：agent 读取结果并修正，全部 blocking=0 才交付。这不是离线 reward，是 agent 自身的失败反馈。
