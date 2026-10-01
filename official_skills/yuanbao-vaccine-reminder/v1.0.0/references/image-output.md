# 图片生成数据约定

在用户要儿童接种计划／时间表、要基于个人材料整理历史，或只上传疫苗本／门诊材料而没有附带文字时读取。纯附件场景默认执行“整理已接种记录并查看整体规划”，不先追问用途。先联网核对当前官方信息，再把本轮已核对内容归一化为 JSON，调用 `scripts/generate_vaccine_images.py`。

- 有完整通知单：`views` 为 `time` 和 `vaccine`，交付两张 PNG。
- 无通知单（包括未上传或缺页）：`views` 只为 `vaccine`，交付一张 PNG。
- 纯附件且无通知单时，这张 PNG 必须是完整的按疫苗整体规划，不是只列已接种记录的摅要；将可确认的 `actual_records` 按整行绿色／蓝色／原色规则标注进度。
- 脚本会产生 HTML 中间件以保证页面和截图一致，但不向用户交付 HTML。

## 信息分层

- `actual_records`：只有接种记录页明确出现疫苗、剂次和可核对的接种事实，才可写 `status: administered`。
- `timeline`：通知单、门诊安排或用户计划，不是实际接种史。
- `programs[].national`：本轮联网核对的国家免疫程序，不是预约日期。

`columns` 和 `programs` 都必须由本轮官方查询结果提供。生成器不再自动读取包内国家程序缓存；缺任一字段就停止，不用旧版补齐。没有通知单时，可由本轮 `programs` 生成按疫苗视图，不需要 `timeline`。

生成前核对：去重后已确认记录数 = 页面标绿数 = 最终回复声称数。模糊候选只进“待核对”，不能凑成已接种。

“按疫苗看”按整行显示进度：已确认记录覆盖该行 `programs[].national` 列出的全部剂次时，整行浅绿底＋深绿字；只覆盖部分剂次时，整行浅蓝底＋蓝灰字；没有已确认记录时保持原色。模糊、冲突或待核对项不计入完成度；程序路径不确定时不标为全程完成。

## 最小结构

```json
{
  "schema_version": "1.0",
  "report": {
    "id": "不含身份信息的稳定ID",
    "title_time": "按时间看",
    "title_vaccine": "按疫苗看",
    "source_mode": "official_or_material",
    "source_completeness": "complete_or_partial_or_none",
    "source_label": "本轮官方依据或上传材料",
    "program_version": "当前官方版次",
    "published_at": "YYYY-MM-DD",
    "verified_at": "YYYY-MM-DD",
    "views": ["vaccine"]
  },
  "columns": [["birth", "出生时"]],
  "programs": [],
  "timeline": [],
  "actual_records": [],
  "sources": []
}
```

## 行与记录

```json
{
  "age": "18月龄",
  "slot": "18m",
  "exam": "体检",
  "free": [{"id":"mmr2","label":"麻腮风疫苗②","vax":"mmr","dose":"2","source":"notice"}],
  "paid": [],
  "price": "",
  "disease": "麻疹、风疹、流行性腮腺炎"
}
```

实际记录优先用 `item_id` 精确匹配：

```json
{"item_id":"mmr2","status":"administered","date":"2026-08-01","source":"接种记录页","confidence":"confirmed"}
```

“下一站与选择”不属于图片数据，不得渲染进 HTML 或 PNG。在最终文字回复中逐项说明免费／自费、当地实际可供厂家（如已核对）、选择依据和当前结论。没有可靠厂家或自费替代时明确说明待门诊确认，不臆造对比。

## 命令与交付

首次出图前检查 `weasyprint==70.0`、`pymupdf==1.28.2`、Pango/Cairo 和中文字体。Python 包缺失时可用当前沙箱的包源安装固定版本一次；若 WeasyPrint 仍报 Pango/Cairo 或字体缺失，立即停止并说明无法生成图片，不改装浏览器、不轮换下载源。

```bash
python3 /data/skills/yuanbao-vaccine-reminder/scripts/generate_vaccine_images.py \
  --input /data/workspace/VACCINE-IMAGE.json \
  --output-dir /data/workspace/vaccine-images \
  --name 儿童疫苗接种整理
```

返回前检查 manifest 的 `views` 与实际 PNG 数量一致，且每张图存在、非空。只向用户交付 PNG，不交付 HTML 或 manifest。
生成器会覆盖模板自带的 A3 打印缩放、恢复 1810px 画布与 15px 表格字号、分别强制显示两个视图，并只根据 PDF 文字块的实际底部裁剪；不用表格边框绘制块计算高度。
纯附件场景交付后可简短说明已确认记录和待核对项，但不得因未获保存授权而调用 `make-things`。
