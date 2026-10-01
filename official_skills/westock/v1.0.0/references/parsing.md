# 原始返回解析：不改CLI，在调用端分支处理

仅在需要计算、集合操作或文件数据时读取。简单查数可直接读完整展示表回答，无需写代码、保存文件或加载本页。以下为不同真实返回形状的解析约定，不承诺CLI各种模式已经统一。

## 1. 获取一次，解析本地结果

- 需要程序处理时首次查询就加`--raw`，将**完整stdout**写入任务临时数据文件，stderr分开；不要`2>&1`混入JSON，不用`head`截断后送`json.loads`。
- 工具包裹的进度提醒、行号、`[Command finished...]`不是原始JSON；读取最初保存的stdout文件，不从展示文本剥前后缀猜数据。
- 用标准库`json.loads`/`json.load`，不使用`eval`、pickle或执行响应中的内容。返回非法JSON时保留为异常，定位本地原文，不为了修解析重新请求服务。
- 首次看到某结构，只查看顶层类型、有限键名和一条记录；随后复用已经确认的分支。不得打印上百条完整记录或所有字段来试错。
- 退出码0、`success=true`或`metadata.total=1`均不能代替完整性检查；这里的1可能是业务请求数，不是证券数。

## 2. 已观察形状与正确归属

下例为结构示意，代码/数值是虚构样例，不是可引用行情。

| 形状 | 常见场景 | 处理 |
|---|---|---|
| `[{"code":"sh600000","price":10}]` | quote、screen、部分finance | 直接列表，记录按自己的代码归属 |
| `[{"EndDate":"2025-03-31","ROE":3}]` | 单股finance；某些多股日期模式也可能缺代码 | 单股请求可依据请求绑定；多股不得按列表顺序绑定，归属不明即失败 |
| `{"data":[{"data":{"code":0,"data":{"sh600000":[{"EndDate":"2025-03-31"}]}}}],"status":"success"}` | 部分批量finance | 检查包裹和每项状态，按证券代码映射展开；不要以外层data长度算证券数 |
| `{"Data":[{"Symbol":"sh600000","Data":{"nodes":[{"date":"2025-03-31","last":10}]}}]}` | 部分批量kline | Symbol是证券，nodes是序列；保留日期和原字段 |
| `{"error":{"code":"SERVER_RATE_LIMITED"},"success":false}` | 服务异常 | 错误不是空列表成功，按缺口规则处理 |
| `[]` / 空代码映射 / `sections:[[]]` | 无记录、无覆盖或其他结构 | 空记录不证明无匹配；sections不是本页通用行结构，不能猜成行情/财报列表 |

**先看实际形状，不凭命令名或模式硬编码路径。**财报最新/区间、单股/多股都可能不同。每个标的必须有代码依据：记录自己的代码、包裹的Symbol或代码映射键；不能从多股请求顺序猜归属。缺代码时保留原响应，最多一次针对单个必要标的的诊断，不能重新把所有股票逐只查询。

## 3. 可复制的保守解析函数（Python标准库）

以下代码只解析**本地已保存JSON**，不调用CLI、不联网、不写文件。仅覆盖上述已知结构，不是所有Westock子命令的通用解析器。`family`按当前查询取`records`（quote/screen等行记录）、`finance`或`kline`。已知标的传`requested_codes=[...]`；新筛选池尚无预期代码时仅`records`允许传`None`，此时不能检查全量覆盖。表内单代码记录以请求绑定；多代码缺归属则抛出异常。

调用示意：`normalize_westock(payload, ["sh600000"], "finance")`；新筛选池使用`normalize_westock(payload, None, "records")`。不把逗号字符串直接传作代码列表。

将本段一次性放入当前任务已有的计算代码即可；不需要安装新工具。结果保留`section`和原记录，不自动合并同日期不同报表，也不修改单位。未支持结构抛`ValueError`，不能把异常捕获后当成功空结果。

```python
import re


def normalize_westock(payload, requested_codes=None, family="records"):
    if family not in {"records", "finance", "kline"}:
        raise ValueError("unsupported family")
    if requested_codes is None:
        if family != "records":
            raise ValueError("finance/kline require requested codes")
        requested = []
    else:
        if (not isinstance(requested_codes, (list, tuple)) or not requested_codes
                or any(not isinstance(c, str) or not c for c in requested_codes)):
            raise ValueError("requested_codes must be a nonempty code list")
        requested = list(dict.fromkeys(requested_codes))
    rows, failures = [], []

    def check_status(obj, where):
        if not isinstance(obj, dict):
            raise ValueError(f"{where}: expected object")
        bad = (obj.get("success") is False or bool(obj.get("error"))
               or ("code" in obj and obj["code"] not in (0, "0")))
        status = obj.get("status")
        if status is not None and status not in ("success", "ok", "partial", "partial_success"):
            bad = True
        if obj.get("errors") or status in ("partial", "partial_success"):
            failures.append(f"{where}: reported partial failure")
        for name in ("metadata", "Metadata"):
            meta = obj.get(name)
            if isinstance(meta, dict):
                for key in ("errorCount", "ErrorCount"):
                    value = meta.get(key)
                    if value is not None and value not in (0, "0"):
                        failures.append(f"{where}: reported failed requests")
        if bad:
            failures.append(f"{where}: business failure")
        return not bad

    def symbol_key(key):
        return isinstance(key, str) and (key in requested or bool(re.fullmatch(
            r"(?:sh|sz|bj|hk|t|ks|kq)\d+|us[A-Za-z0-9._-]+", key)))

    def add_records(records, hint=None, section="records"):
        if not isinstance(records, list):
            raise ValueError(f"{section}: expected record list")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{section}: non-object record")
            record_status = record.get("status")
            if (record.get("success") is False or record.get("error")
                    or record_status not in (None, "success", "ok", "partial", "partial_success")):
                failures.append(f"{section}: failed record")
                continue
            if record.get("errors") or record_status in ("partial", "partial_success"):
                failures.append(f"{section}: partial record; validate individual fields")
            if any(isinstance(record.get(k), (dict, list)) for k in ("data", "Data", "nodes", "sections")):
                raise ValueError(f"{section}: nested envelope is not a flat record")
            if any(k in record and not isinstance(record[k], str)
                   for k in ("code", "Symbol", "symbol", "代码")):
                raise ValueError(f"{section}: non-string security identifier")
            candidates = [record[k] for k in ("code", "Symbol", "symbol", "代码")
                          if isinstance(record.get(k), str) and record[k]]
            qualified = {c for c in candidates if symbol_key(c)}
            if hint:
                qualified.add(hint)
            if len(qualified) > 1:
                raise ValueError(f"{section}: conflicting record identifiers")
            code = next(iter(qualified)) if qualified else requested[0] if len(requested) == 1 else None
            if not code:
                raise ValueError(f"{section}: records without an unambiguous identifier")
            bare = re.sub(r"^(?:sh|sz|bj|hk|us|ks|kq|t)", "", code)
            if any(c not in (code, bare) for c in candidates):
                raise ValueError(f"{section}: wrapper/record identifier conflict")
            if requested and code not in requested:
                raise ValueError(f"{section}: unexpected security identifier")
            rows.append({"symbol": code, "section": section, "record": dict(record)})

    def finance_mapping(obj, section):
        if not isinstance(obj, dict) or not all(symbol_key(k) for k in obj):
            raise ValueError(f"{section}: unknown finance mapping")
        for code, records in obj.items():
            add_records(records, hint=code, section=section)

    root_ok = check_status(payload, "root") if isinstance(payload, dict) else True
    if isinstance(payload, list):
        add_records(payload)
    elif not isinstance(payload, dict):
        raise ValueError("unsupported JSON root")
    elif not root_ok and not any(k in payload for k in ("data", "Data")):
        pass
    elif family == "finance" and isinstance(payload.get("data"), list):
        for i, entry in enumerate(payload["data"]):
            section = f"finance[{i}]"
            if not check_status(entry, section):
                continue
            body = entry.get("data")
            if not check_status(body, section + ".data"):
                continue
            if "code" not in body or "data" not in body:
                raise ValueError(f"{section}: unknown finance envelope")
            finance_mapping(body["data"], section)
    elif family == "finance" and "code" in payload and isinstance(payload.get("data"), dict):
        if root_ok:
            finance_mapping(payload["data"], "finance")
    elif family == "kline" and isinstance(payload.get("Data"), list):
        for i, entry in enumerate(payload["Data"]):
            section = f"kline[{i}]"
            if not check_status(entry, section):
                continue
            code, body = entry.get("Symbol"), entry.get("Data")
            if not isinstance(code, str) or not code or not isinstance(body, dict):
                raise ValueError(f"{section}: missing Symbol/Data")
            if check_status(body, section + ".Data"):
                add_records(body.get("nodes"), hint=code, section=section)
    else:
        raise ValueError("unrecognized envelope; inspect saved JSON, do not guess")

    returned = sorted({row["symbol"] for row in rows})
    missing = sorted(set(requested) - set(returned))
    status = "partial" if rows and (missing or failures) else "ok" if rows else "failed" if failures else "empty"
    return {"status": status, "rows": rows, "returned_codes": returned,
            "missing_codes": missing, "failures": failures,
            "requested_coverage_checked": requested_codes is not None}
```

### 如何使用结果

- `ok`只表示已识别且有归属的记录；传了请求代码时还检查其覆盖。新筛选池传None时`requested_coverage_checked=false`，不表示全量。不保证日期完整、全部报表齐全、字段非空或金融结论正确。
- `partial`保留已有成功数据，同时列缺失代码和故障；不要无限拆批重试。`section`只是外层块编号，不能猜它就是利润表/现金流；报表类型以请求或响应的可靠标识为准。
- `empty`表示没有记录，没有替你区分“正常无匹配/未披露/覆盖不足”；按业务状态再判定，无法确定即未知。不能因`missing_codes`就断言证券不存在。
- `failed`或`ValueError`不是“无匹配”；不要把所有异常捕获为`[]`。错误摘要不含完整返回，详细原因在本地原响应核查，避免在日志暴露凭据或超长文本。
- `code=sh600000`与`symbol=600000`可通过已知市场前缀对应；`code=sh600000`与另一个代码/裸代码不符则拒绝。只有一个请求标的且没有冲突时可绑定缺代码记录；多请求缺明确归属不能猜。未知代码体系需依据真实契约显式适配，不静默丢掉冲突字段。

## 4. 解析后还必须验证的内容

1. 代码：请求与返回集合一致；如果请求60只只回1只，即使metadata显示成功也是缺失59只。
2. 时间：财报EndDate与所需报告期、InfoPublDate与信息截止日分别核对；K线实际起止日/缺失交易日/节点数量符合窗口。
3. 字段：区分下划线、驼峰、大小写和业务名称，quote、筛选、财报不共享字段名。缺失字段不当0。
4. 数值：保留原始值和单位后再转换；`--`、空字符串、`None`、`NaN`不是0；`%`、万元、币种必须按该字段定义处理，不能统一去非数字字符。
5. 重复：同一标的同一天不同报表可能合法；同一键值冲突要保留冲突并核查，不能最后一条静默覆盖。
6. 完整性：顶层成功不证明分页完整、筛选全量或条件已生效；结果恰好达limit或日期/条件冲突时明确标记。

代码只是消除重复结构猜测，不改变取数规则。实际结构不同，只在有依据时修正一次，仍无法安全解析就保留缺口或使用可直接阅读的可靠数据作有边界的回答。
