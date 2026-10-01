---
name: pptx
description: "处理所有与 .pptx 相关的任务：创建演示文稿、编辑现有幻灯片、读取或提取内容、按模板生成、合并或拆分文件，以及处理版式、备注和评论。只要用户提到 deck、slides、presentation，或出现任何 .pptx 文件名（无论后续用于编辑、分析、总结或转写），都应使用此技能。"
---

# PPT 技能

从模板生成 PPT，模板在 `$YB_SKILL_PATH/pptx/templates`。
**目录约定**（任务开始时先确定，两个占位符都必须替换为真实绝对路径）：
- `WORK_DIR="<当前工作目录的真实绝对路径>"`：用户工作区，只存放最终交付文件（由 `apply_plan --output-dir` 写入）。
- `RUN="<系统临时目录的真实绝对路径>/ppt_runs/<run_id>"`：本次任务的运行目录，只存放中间产物（解包文件、tsv、报告等）。
- `<run_id>` 用主题短名（如 `strategy_deck`）。**每生成一份新 PPT 对应一个新的 `<run_id>`**；用户要求修改已生成的 PPT 时，沿用该 PPT 原来的 `$RUN` 继续迭代，不要另起新目录。
- 禁止在 skill 目录下创建任何文件；禁止把 `$RUN` 内的路径作为交付路径报告给用户。



## 硬规则
- 模板库 `$YB_SKILL_PATH/pptx/templates` 是**只读**的：绝不在原地修改模板。所有解包、编辑、打包都在 `$RUN`（如 `$RUN/unpacked`）这个独立临时工作目录里进行——`prepare_deck.py` 已自动解包到那里，照用即可。
- 基于模板生成，但模板是画布——按需取用：删掉不相关的页、复制好用的版式多次使用、自由重排顺序。不必用模板的全部页面。
- 不从零创建 PPT；不要用 `python-pptx` 读取、排查或重建 PPT，也不要写临时 `apply_*.py`。
- 插图只替换模板已有图片位；没有图片位就不新增。但**模板自带的库存配图不能留**：选中页里**每个显著图位**（占版面较大的照片位）都必须用 `image_generation-generate` 按本次主题**重新生成一张并替换**，每个图位一张**不同**的图。原样保留模板照片会被 `check_images` 以 `untouched_template_image` 阻断交付。
- 交付前 `verify_content.py`、`check_layout.py`、`validate_pptx.py`、`check_images.py` 的 blocking 必须全为 0（`apply_plan` 已自动串好）。
- 不得向用户返回 `$RUN` 内的临时路径作为最终产物；只报告 `apply_plan` headline 中的 `final_pptx` 路径。

## 效率纪律（轮次有限，先搭骨架再补内容）

模型工具轮次有限，跑偏就交不出产物。务必：
- **检索克制**：`web_search`/`picture_search` 全程合计 ≤ 3~4 次，先把页面骨架和文案写出来，再按需补少量数据/图。不要在动手前反复搜索。
- 每个阶段尽量**一次 bash 调用**跑完（下方已用 `&&` 串好）。

## 最优顺序（照此走，少走回头路）

文本和图片必须在**同一次** `apply_plan` 里一起传入——别先跑一次纯文本 `apply_plan`（会触发 `image_blocking`）再补图重跑，那会白跑一整条流水线。标准 8 步：

1. `prepare_deck.py "$RUN" --template <模板>`：打开选定模板看全部页结构。
2. `prepare_deck.py "$RUN" --slides 1,3,5`：选页/复制/重排，生成 `deck.selected.json`（含稳定 `ref`、`texts`、`image_slots`）。
3. 写 `$RUN/content_lines.tsv`：把每个标题/正文 `ref` 的文案写好（见「内容写作规范」）。
4. 配图：对 `deck.selected.json` 里**每个显著图位**调一次 `image_generation-generate`，把结果写进 `$RUN/images.json`（需要微调版式时再加 `$RUN/layout_ops.json`）。图可并行生成。
5. **一次** `apply_plan.py "$RUN" --template <模板> --lines content_lines.tsv --images images.json [--layout layout_ops.json] --output-dir "$WORK_DIR"`。
6. 看 headline：`ok:true` 时 `final_pptx` 即用户工作目录中的最终交付路径；`ok:false` 按 `finalize_report.json` 修 `content_lines.tsv`/`images.json` 重跑**同一条**命令。
7. 最多修 2 轮，超预算就停并报告 blocking。
**环境依赖故障处理**：当某条脚本命令因依赖缺失失败（`ModuleNotFoundError`、`ImportError`、`command not found` 等）时，执行一次 `python $YB_SKILL_PATH/pptx/scripts/ensure_deps.py`，然后**重试原命令一次**。全任务 `ensure_deps` 最多执行一次；补齐后仍失败，则是环境问题而非依赖问题，停止并向用户报告，不要循环重试。


下面各章节是每一步的细则。

## 快路径（每块一次 bash 调用）


### 选模板：读 manifest.json 选模板，再用 yuanbao-cli 下载

模板库按 `类别 → 场景 → 风格` 三层组织，全部元数据集中在 `$YB_SKILL_PATH/pptx/manifest.json`。根据用户需求从下表定位类别/场景，推导关键词后用 `grep` 快速筛选，再从结果中语义选定；grep 结果为空时去掉一层条件放宽，或直接 `cat` 全文。

- **商业**：产品方案介绍 / 行业研究报告 / 投资路演 Pitch Deck / 新品发布会 / 财报、业务数据 / 述职、月报、季报 / 项目立项、复盘 / 品牌升级、活动招商 / 商务合作提案 / 全员大会、年会
- **学校**：K12教师课件 / 学术会议、学术报告 / 高校讲座、公开课 / 本科、硕士答辩 / 博士开题、中期、盲审 / 课程作业、小组汇报 / 社团、学生会活动
- **政府**：政府工作报告 / 政府重要会议简报 / 党建汇报、主题党日 / 红色教育、党史学习 / 国企工作总结 / 部门、个人述职 / 事业单位汇报（公检法、医院、高校行政）
- **设计**：TED风格演讲 / 极客、科技、AI主题 / 作品集（设计、摄影、插画） / 知识沉淀、自媒体图文（杂志风） / 艺术、文化主题讲座 / 通用展示（国际主义风）

```bash
# A. 根据用户需求推导关键词，grep 快速定位候选（多条件串联逐步收窄）
cat $YB_SKILL_PATH/pptx/manifest.json | grep "关键词1" | grep "关键词2"
# 例：旅游活泼风格  → cat ... | grep "人文\|旅" | grep "明媚\|彩"
# 例：科技深色风格  → cat ... | grep "科技\|AI" | grep "黑\|深"
# 若结果为空，去掉一层 grep 放宽；仍不够再直接 cat 全文
cat $YB_SKILL_PATH/pptx/manifest.json
```

从 manifest 的每个条目中综合判断：
- `style`：风格/配色描述，用于语义匹配
- `sample`：模板示例文字，反映实际内容风格
- `slides`：页数，按需求范围筛选
- `pages`：页面结构摘要（封面/目录/内容/结束等），判断版式是否合适
- `path`：选定后用于下载，格式为 `类别/场景/风格.pptx`

选定后，用 `yuanbao-cli download` 把模板下载到本地：

```bash
# B. 下载选中的模板（path 即 manifest 中的 path 字段值）
# 首次顺带补齐依赖（已就绪则毫秒级跳过）
mkdir -p "$RUN" && yuanbao-cli download --skill pptx "<path>" --output-dir "$RUN" --output template.pptx
```

```bash
# C. 打开模板查看全部页结构（决定保留/复制哪些页）
python $YB_SKILL_PATH/pptx/scripts/prepare_deck.py "$RUN" --template "$RUN/template.pptx"
```
```bash
# D. 选页/复制/重排 + 清理 + 生成最终结构（输出稳定 ref，写进 deck.selected.json）
python $YB_SKILL_PATH/pptx/scripts/prepare_deck.py "$RUN" --slides 1,3,5,8
```

**选页策略**：模板是你的画布，灵活使用——
- 只保留与主题相关的页面，其余全删。
- 好用的版式（如内容卡片页、数据页）可重复使用：`--slides 1,4,4,4,7` 会复制 slide4 三份，各自独立编辑。
- 页数由用户需求决定，不必凑满模板原有页数，也不必受模板限制。

不要手写大 JSON。把文案写进 `$RUN/content_lines.tsv`，每行：
`ref<TAB>replace|clear|keep<TAB>文本`，同一框多段用 `||` 分隔。下一步 `apply_plan.py` 会自动据此生成并应用计划（见下）。每个 text 只用 `replace`、`clear`、`keep`。引用复制 `ref`，不要猜页码或 shape。
选模板时综合考虑用户的页数、受众、风格和主题；查看结构时读 `deck.selected.json` 每页的 `texts`（含 `ref`/`kind`/`text`/`bounds`/`autofit`），不要假设其他字段。
**模板原文必须改写**：`texts` 里 `kind: title|body` 的文字若原样保留不动，`verify_content` 会以 `untouched_template_text` 阻断交付——每个标题/正文 `ref` 都要 `replace` 成你的内容或 `clear`，不能留模板示例文字。`keep` **只用于品牌名/页码等装饰文本**；对标题/正文用 `keep` 保留模板原文同样会被阻断（与漏改一视同仁）。
`kind: title` 只放短标题/标签，正文和多行要点优先放 `kind: body`；小框不承载段落。
不要把“联系我们/地址/邮箱/电话”类页面改成密集内容页；若必须用作结束页，只放短行动项或讨论页。

## 内容写作规范（务必遵守）

- **短**：标题/要点用 PPT 常见的简短 bullet（标题≤约14字，要点≤约24字），不要把长句整段塞进标题框，否则溢出。一个槽位预留几行就写几行。
- **按槽位语义填**：看 `deck.selected.json` 每个 `ref` 的 `text`/`bounds` 判断它是什么位。**数字/短标签位**（模板原文是 `117`/`60%`/`21万亩` 这类纯数字+短单位、框又矮又小）**只放短数据**，配套标签也要短（如"种植面积""同比+12%"）。**严禁把整句话/长叙述塞进数字位**——会炸框压住相邻卡片，并被 `verify_content` 以 `data_slot_misuse`、`check_layout` 以严重 `text_overflow` **阻断交付**。长叙述放正文/要点（`kind: body`）区。
- **内容要切题**：每个 `ref` 填与本页主题一致的内容，别把别的主题硬塞进来（如草莓数据页不要塞葡萄句子）；数据要与页面标签对应。
- **不加序号**：不要在文案里写带圈序号 ①②③（模板自带编号；脚本也会自动删除）。普通编号如确需，用模板原有样式。
- **高亮只标关键词**：需要强调时只高亮核心词或数字，不要把整句、整个短语都标成高亮。
- **按语义换行**：分段（独立 `<a:p>`）用 `||`；同段内软换行直接在文本里写**真实换行**。按断句换行，不要把一长串硬塞一行，也不要让标点出现在行首（避头尾）。即使误写了字面的 `\n`/`\t`，脚本也会自动还原为真换行/制表（不会显示成 `¥n`）；但仍建议直接用真实换行或 `||`，别把转义当普通字符堆在文案里。
- **版式要有节奏**：按主题和数据挑选**不同**版式，图文/左右/数据页交错使用，避免连续多页用同一种版式；可围绕主题适当扩展多维度数据（趋势、对比、占比等），让内容更丰富有节奏，而不是机械复制同款页。
- **角标/页脚**：`inspect_deck` 输出的 `master_layout_texts` 列出写死在母版/版式里的角标文字。若这些角标需要改写，直接编辑对应 `ppt/slideLayouts/*.xml` 或 `ppt/slideMasters/*.xml` 里的 `<a:t>`（仅改文字，别动结构）；页面内的小角标用正常 `ref` 改写。
- **真实数据**：用搜索到的真实数值，不要留 `N/A`、`待补充`、`TODO`、`暂无数据` 等占位字段；图表里的数据也要一并改写，别漏改。
- **怪符号**：不要在词与词之间乱插斜杠（如 `让AI/真正`、`，/`）；脚本会自动清理，但你也不应生成。

最小示例（content_lines.tsv 每行；也可手写 content_plan.json）：
```
slide5:shape3	replace	2026年中国新能源汽车出海战略
slide5:shape9	replace	要点一||要点二||要点三
slide9:shape5	clear
```

## 配图：每个显著图位按主题生成新图（必做，在 apply_plan 之前完成）

模板里的照片是**占位库存图**，必须换成贴合本次主题的新图。**配图要和文案一起，在下一步 `apply_plan` 的同一次调用里传入**——不要先跑纯文本再补图。流程：

1. **找图位**：从 `deck.selected.json` 每页的 `image_slots` 取 `ref`（形如 `slide5:image1`）。**用这里的 ref**——选页/复制后整副 deck 的页号已重排，复制出来的副本是新页名（如 `slide23:image1`），千万别用原模板页号或 `deck.json` 的旧编号。
2. **逐个生成**：对每个显著图位调一次 `image_generation-generate`（`dst_intent:"Text2Image"`，prompt 写清画面内容+风格，贴近图位的横竖比例以减少裁切）。**每个图位一张不同的图**，即使版式相同也要按该页主题分别生成，绝不复用同一张。图之间互不依赖，可并行生成以省轮次。
   - 若是**文字会叠在其上的背景图/满版图**：prompt 要按该页文字色拉开明度——深色字配浅底、白字配深底，文字区低对比留白。普通插图不必管。
3. **写 `$RUN/images.json`**：每项用 `ref` 指定图位，`image` 可直接填生成返回的 **http(s) URL**（脚本会自动下载），也可填本地路径。这个文件在下一步随 `apply_plan --images` 一起传入，**本步不要单独跑命令**。

```json
[
  {"ref":"slide5:image1","image":"https://.../gen1.png"},
  {"ref":"slide23:image1","image":"https://.../gen2.png"}
]
```

要点：
- **配图预算**：只处理**显著图位**（占版面较大的照片位）；小图标/装饰角标不计，别为装饰小图浪费轮次。
- `apply_plan` 自动按图片框纵横比做居中 cover 裁剪（不拉伸）；图位若自带旋转（斜放相框），会**自动反向旋转源图使照片显示为正**，无需你处理。
- 替换会写入**独立媒体**、只动该图位——即使多页复制自同一模板页（共享同一张原图），各页也能是不同的图，不会互相覆盖。
- headline 里 `images_failed>0` 说明有图位没对上：八成是 ref 用错（要用 deck.selected.json 重排后的 `slideN:imageK`），照提示改 images.json 重跑。
- 交付前 `check_images` 会检查：选中页的显著图位若仍是模板原图，`image_blocking>0` 并阻断——补生成那几个图位的图后重跑。小图标/装饰角标不计。

## 应用 + 交付（一条命令搞定，文本 + 图片一起传）

`apply_plan.py` 一次完成：plan_from_lines → replace_text → 图片替换 → finalize_run（内含 verify_content + check_layout + 打包）。**文本和图片在同一次调用里一起传**（有图位就带 `--images`），不要分两次跑。**不要再单独调用 dry-run / replace_text / verify_content / check_layout / finalize_run**——那是多余的往返，容易在中途轮次耗尽。

```bash
python $YB_SKILL_PATH/pptx/scripts/apply_plan.py "$RUN" --template "$RUN/template.pptx" \
  --lines content_lines.tsv --images images.json --output-dir "$WORK_DIR"
```
没有图位时省略 `--images`；需版式微调再加 `--layout layout_ops.json`（见下）。

输出 headline：`ok`、`final_pptx`、`verify_blocking`、`layout_blocking`、`validate_blocking`、`image_blocking`、`applied`、`images_ok`、`images_failed`。
- `ok:true` → `final_pptx` 是脚本直接生成在 `--output-dir` 下的最终交付路径；向用户报告该路径，不得把 `$RUN` 下的临时路径当作交付结果。
- `ok:false` → 看 `$RUN/finalize_report.json`，**优先只修 content_lines.tsv**（缩短/改 clear/补文案），重跑同一条 `apply_plan.py`。
- 文本替换报错（exit≠0）→ headline 带 errors，只修对应 `ref` 行后重跑，别读脚本、别写新脚本。
- `validate_blocking>0` 极少见（结构损坏）→ 看 `$RUN/validate_report.json`，通常重跑 `prepare_deck`→`apply_plan` 即可；不要手改 XML 结构。
- `image_blocking>0` → 看 `$RUN/images_report.json` 列出的 `untouched_template_image` 图位，给这些 `ref` 各生成一张主题图、补进 images.json 重跑。

## 版式微调（可选，处理溢出/压字）

优先用「缩短文案」解决溢出；当文案已合适但框装不下、或 `check_layout` 报 `overflow`/`overlap` 时，可让文本框自适应或微调几何——写一个 `$RUN/layout_ops.json`（数组），随 apply_plan 一起跑：

```bash
python $YB_SKILL_PATH/pptx/scripts/apply_plan.py "$RUN" --template "$RUN/template.pptx" --lines content_lines.tsv --layout layout_ops.json --output-dir "$WORK_DIR"
```

每项一个 `ref`：
- 让字自动缩小适配固定框（最常用）：`{"ref":"slide5:shape3","autofit":"normal"}`，可加 `"fontScale":90`（百分比）。
- 移动/缩放文本框（EMU，914400=1英寸；增量用 `dx/dy/dcx/dcy`，绝对用 `x/y/cx/cy`）：`{"ref":"slide7:shape2","box":{"dy":-180000,"dcy":360000}}`。

`bounds`（坐标尺寸）和 `autofit`（当前模式）在 `deck.selected.json` 的每个 text 里都有，据此判断要不要调。版式微调失败不阻断交付，只记录在报告里。

## 修复预算

按 `apply_plan` 的 headline 迭代，最多修 2 轮（`content_lines.tsv` 为主，必要时加 `layout_ops.json`）；超预算就停止并报告 blocking，不要写新的 PPT 生成脚本，也不要用 `python-pptx` 排查。
`check_layout` 的 `text_overflow`：轻度超框是 **warning**；但**远超框高（约≥2 倍、且非模板原生、非 normAutofit）会升级为 blocking**，必须修——缩短该 `ref` 文案、改 `clear`、或用上面的 `autofit`/扩框。`verify_content` 的 `data_slot_misuse`（数字/短标签位被塞长句）是 **blocking**，把长内容挪到正文区或改短。`circled_number/stray_slash/invalid_data/literal_escape` 是 warning，提示清理文案。
内容抽查只看 `$RUN/finalize_report.json`（含 verify/layout 结果）或 `inspect_deck` 输出，不要导入 `pptx` / `Presentation`。排版/配色建议见 [design.md](design.md)（按需阅读）。

---

## 边界说明

`$YB_SKILL_PATH/pptx/scripts/finalize_run.py` 的四项校验（`verify_content`、`check_layout`、`validate_pptx`、`check_images`）是 **rollout 硬关卡（hard gate）**：agent 在 rollout 内读取其结果并修正，全部 blocking=0 才能交付。这不是离线 reward，是 agent 自身的失败反馈。
