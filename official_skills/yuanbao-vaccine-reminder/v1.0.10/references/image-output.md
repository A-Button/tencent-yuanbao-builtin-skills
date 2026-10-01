# 图片生成数据约定

仅在整理接种历史／整体计划或纯上传材料时读取。先核对官方依据和真实材料，再填 JSON；正常路径只运行固定入口，不列目录、不阅读生成器源码、不现场写绘图代码。

上一轮邀请上传疫苗本后，用户只发来接种材料，也按纯上传处理：本轮回应原问题并交付应有的图片，不先问是否需要出图。图片内容依据记录、完整通知单和适用程序填入下述结构；不能用临时手填的记录表和状态表替代。

## 单次执行与交付

```bash
python3 /data/skills/yuanbao-vaccine-reminder/scripts/generate_vaccine_images.py --input /data/workspace/VACCINE-IMAGE.json --output-dir /data/workspace/vaccine-images --name 儿童疫苗接种整理 --install-missing
```

`--install-missing` 仅用于允许安装依赖的元宝执行沙箱，不在用户本机安装。入口自动校验数据、检查固定版本依赖（WeasyPrint 70.0、PyMuPDF 1.28.2），缺包时安装一次，再检查系统渲染库和中文字体，生成并检查 PNG。失败就报告具体缺口，不轮换包源／浏览器／绘图库。排错时才读取对应源码。

输出 manifest 的 `delivery.files` 是唯一附件清单（真实绝对路径、尺寸、字节数）；`summary` 是回复统计依据。有完整通知单交付 `time,vaccine` 两图，无通知单只交付 `vaccine` 一图。HTML/PDF/manifest 都不是用户交付物。

1. 把 `delivery.files[].path` 交给 `present_files` 登记。
2. 回包确认相同路径后，原样使用 `delivery.media_info` 放入最终回复；它是 `file/path` 数组，不是 image/url。绝不拼造 `http://yb.woa.com/...` 或其他网址。
3. 回包给出不同路径／官方媒体引用时，仅按当次工具协议使用真实返回值，不能自行猜测转换。登记失败、回包为空或引用无法确认时，说“图片已生成但未成功发送”。生成、登记、客户端可见是三个不同状态，不能仅凭脚本清单断言已展示。

`--no-screenshots` 仅供包外测试，返回 `not_rendered`、无附件清单，不能拿它宣称已出图。

## 数据结构（schema 2.0）

```json
{
  "schema_version": "2.0",
  "report": {"id":"不含身份信息的稳定ID","program_source_id":"national","views":["vaccine"]},
  "columns": [["birth","出生时"]],
  "programs": [{"vax":"疫苗键","name":"已核对名称","disease":"预防疾病","national":{"birth":"1"},"source_ids":["national"],"path_confirmed":true}],
  "timeline": [],
  "actual_records": [],
  "coverage": [],
  "sources": [{"id":"national","authority":"national","title":"实际文件标题","url":"实际官方页面URL","version":"实际版次或文件日期","published_at":"YYYY-MM-DD","verified_at":"YYYY-MM-DD","scope":"适用年龄、地区及程序范围","applicability":"current","applicability_note":"已核实的现行或过渡适用依据"}]
}
```

示意占位值不能直接用于出图。`programs` 是完整的已核对疫苗表，不只包含已接种项目；需要时可增加 `route,volume,code,branch,audience`。来源 `applicability` 可为 `current` 或有核实依据的 `still_applicable`，不能只按年份判定。每个 program 的 `source_ids` 都必须存在；`report.program_source_id` 指向国家程序。版次、发布日期、核对日期由该来源自动生成，重复填写却不一致会拒绝生成。结构检查不证明来源真实性或医学正确性，仍由阅读官方材料核实。

## 真实事件与覆盖映射

实际记录只写一次：

```json
{"event_id":"record-001","record_type":"actual","vax":"疫苗键","dose":"1","date":"YYYY-MM-DD","source":"接种记录页定位","status":"administered","confidence":"confirmed"}
```

- 每条是一个实际接种事件；以疫苗、剂次、日期去重并保留稳定 `event_id`，不能把联合苗拆成几条已接种事件。日期无法确认可留空，不用程序日期补。待核对项用 `status:unknown,confidence:uncertain`。
- `vax+dose` 对应图中疫苗行与剂次，通知单条目还可用 `item_id` 匹配。多个实际剂次不能塞进一条记录。
- 联合苗覆盖另放 `coverage`：`{"source_event_id":"record-001","vax":"目标成分键","dose":"1","confidence":"uncertain"}`。只有确有门诊确认依据时才写 `confidence:confirmed,verification:clinic_confirmed,basis:"实际确认依据"`；不能自造确认。
- coverage 不能写 `status:administered`，不能增加实际记录数量。缺原事件、重复映射、重复记录或来源不一致时停止生成并修正输入。
- `summary.confirmed_event_count` 是回复中“已确认接种记录”数；`covered_program_dose_count` 是当前程序覆盖剂次数，两者不要求相等。覆盖所有确认路径剂次才整行绿，部分覆盖蓝，尚无确认记录保持原色；`path_confirmed:false` 禁止标全程完成。

## 通知单与图片范围

有完整通知单时填 `timeline`，并用 `report.views:["time","vaccine"]`。每行例如：

```json
{"age":"材料参考年龄","slot":"与columns一致的键","exam":"材料体检安排","free":[{"id":"notice-1","label":"材料疫苗名称与剂次","vax":"疫苗键","dose":"1","source":"notice"}],"paid":[],"price":"","disease":"材料说明"}
```

timeline 表示门诊安排／计划，不是接种史；无通知单留空，由程序生成按疫苗视图。图片不放下一站厂家／费用选择卡；文字只回答本轮必要选择，不强制逐项展开。
