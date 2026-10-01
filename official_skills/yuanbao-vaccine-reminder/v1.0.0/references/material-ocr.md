# 接种材料快速识别

上传一页、几页或整本时都先做一次材料分流，再决定哪些页进入详细识别。目标是少扫无关页，同时保留模糊内容的核对入口。

## 固定流程

1. 将本轮所有图片一次性交给 `scripts/triage_vaccine_materials.py`。脚本按文件哈希去除完全重复图片，并行执行一次低分辨率 OCR，只用于识别页面类型。
2. 按当前问题选页：
   - 只上传疫苗本或门诊材料、没有附带文字：按“整理已接种记录并查看整体规划”处理，识别 `actual_record` 和 `appointment_notice`，不先追问用途。
   - 整理或保存已接种记录：只详细识别 `actual_record`。
   - 查询下一针：识别 `actual_record` 和 `appointment_notice`；只有确实需要按年龄计算时，额外从一张 `identity_page` 读取出生日期。
   - 保存、长期维护或需区分多个孩子：若用户未提供姓名／称呼，最多从一张 `identity_page` 只读取儿童姓名；姓名模糊则请用户给出稳定称呼，不猜测。
   - 生成材料结果图：识别 `actual_record` 和 `appointment_notice`。
   - `program_reference` 不作为个人接种事实；需要最新程序时走官方信源，不重复 OCR 用户上传的旧程序表。
3. 默认只提取疫苗名、剂次和实际接种日期。用户询问产品或下一针选择时才增加厂家；批号、部位、门诊、签名等只用来辅助确认记录，不默认逐字段转录。
4. 每个选中页面先做一次完整识别。只有某个会改变结论的字段不清楚时，才对该局部裁剪再识别一次。局部复核后仍不确定，就标为待核对或请用户补拍该区域。
5. 详细识别结果按“疫苗＋剂次＋实际日期”去重。页数、记录数和最终回复数字必须闭环；不得用程序日期、相邻行或用户未上传的页面补全事实。
6. 纯附件场景的识别完成后直接进入图片交付：有完整 `appointment_notice` 时交付两张；没有时交付一张完整的按疫苗规划图，并用已确认记录标注进度。不因用户没有附带文字而只返回“收到”或询问想做什么。

## 命令

整理已接种记录：

```bash
python3 /data/skills/yuanbao-vaccine-reminder/scripts/triage_vaccine_materials.py \
  --task history --output /data/workspace/vaccine-materials/triage.json \
  /data/workspace/uploads/*
```

查询下一针且确实需要出生日期：

```bash
python3 /data/skills/yuanbao-vaccine-reminder/scripts/triage_vaccine_materials.py \
  --task next --need-age --output /data/workspace/vaccine-materials/triage.json \
  /data/workspace/uploads/*
```

要保存／长期维护，且用户未提供孩子称呼：

```bash
python3 /data/skills/yuanbao-vaccine-reminder/scripts/triage_vaccine_materials.py \
  --task history --need-child-name --output /data/workspace/vaccine-materials/triage.json \
  /data/workspace/uploads/*
```

如果运行环境没有 Tesseract，脚本仍会完成哈希去重，但页面类型会进入 `review_thumbnail`。此时只人工查看一次缩略图完成分类，再遵守同一选页和停止规则；不要退回整本反复 OCR。

## 执行预算

- 分流阶段：每个唯一图片一次快速 OCR，同一批并行执行。
- 详细阶段：每个入选页面一次；每个关键模糊区域最多再试一次。
- 禁止为了寻找更清楚的结果轮流尝试整页旋转、全页分栏、逐行、滑窗和多套二值化。
- 身份页默认不做详细 OCR；只有年龄计算或保存／多孩子消歧需要时，才从一页读取出生日期和／或儿童姓名。不读取或输出证件号、地址、电话和监护人信息。
