# 文件格式转换

## 核心做法

把用户的转换请求落实为一小段 Python 代码并运行它。核心接口有三个参数：

```python
from yuanbao import yuanbao_convert

resources = ["/path/to/file1", "/path/to/file2"]
target = "目标格式"
output_dir = "path/to/output/dir"

result = yuanbao_convert(resources=resources, target=target, output_dir=output_dir)

if result.error:
    print(f"转换失败: {result.error}")
else:
    print(f"转换结果已保存为: {result.data}")
```

- `resources`：输入文件路径列表。
- `target`：目标格式，如 `pdf`、`docx`、`pptx`、`xlsx`、`png`。
- `output_dir`：输出目录，转换结果写到该目录下。

格式转换不需要先读取文件内容，直接调用 `yuanbao_convert` 即可。

用 bash 运行上述转换代码时，必须设置 `timeout=300000`（5 分钟）。

## 支持的转换

只处理下表列出的转换。源、目标格式不在表内的组合，一律不属于本技能范围，使用其他技能，不要调用 `yuanbao_convert` 碰运气。

| 类别 | 源格式 | 目标格式 |
| --- | --- | --- |
| 图片 | 图片（PNG/JPG 等常见类型） | 图片（PNG/JPG 等常见类型） |
| 图片 | 图片（PNG/JPG 等常见类型） | PDF |
| 文档 | DOCX | PDF |
| 文档 | DOC | DOCX |
| 文档 | PDF | DOCX |
| 文档 | PDF | PPTX |
| 表格 | CSV | XLSX |
| 表格 | XLSX | CSV |
| 表格 | XLS | XLSX |

## 工作流

1. 判断用户是否只是在请求文件格式转换，并且落在“支持的转换”表内。如果用户有其他需求，如生成、总结、翻译、润色、提取表格、OCR、重设计幻灯片、压缩文件或编辑内容，请使用其他技能。
2. 写一段 Python 代码调用 `result = yuanbao_convert(resources=resources, target=target, output_dir=output_dir)`，用 bash 运行并设置 `timeout=300000`，完成转换。
3. 使用 `result.data` 获取转换后的文件路径，并把生成的文件交付给用户；如果转换失败，根据 `result.error` 说明原因，并给出可执行的下一步。

## 范围边界

- 只执行“支持的转换”表内的文件格式转换。
- 必须是真正的**格式转换**，即同一份内容换一种容器/编码。用户上传一个普通 PDF 想“做成 PPT/生成演示文稿”，本质是内容重排与重新设计，**不属于转换**，不要用本技能；只有当 PDF 本身就是待还原为可编辑 PPTX 的幻灯片内容时，才走 PDF → PPTX。

## 目标格式处理

调用前，把目标格式归一化为最简单的扩展名：

- 用户直接给出扩展名时，优先保留为小写扩展名，如 `pdf`、`docx`、`pptx`、`xlsx`、`png`。
- 用户用自然语言描述时，映射到最接近的后端目标扩展名，如“文档”通常是 `docx`，“演示文稿”通常是 `pptx`，“表格”通常是 `xlsx`，“图片”通常是 `png`。

## 批量转换

- 用户要求把多个文件转成同一种目标格式时，把所有文件名称一起传入 `resources`，例如 `resources = ["文件1.docx", "文件2.docx"]`。
- 转换器返回多个输出文件时，一并交付。
- 只有部分文件成功时，交付成功文件，并在可获得信息时明确列出失败文件。

## 错误处理

遇到不支持的转换、文件缺失或不可读、超时或服务故障等错误，使用其他技能或工具解决。