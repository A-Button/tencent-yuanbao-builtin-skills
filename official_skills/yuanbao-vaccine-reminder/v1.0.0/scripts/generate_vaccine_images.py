#!/usr/bin/env python3
"""Generate one or two vaccine PNG views without a browser runtime."""

from __future__ import annotations

import argparse
import copy
import html as html_lib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def esc(value: object) -> str:
    return html_lib.escape("" if value is None else str(value), quote=True)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dose_text(value: object) -> str:
    return str(value).replace("、", "-").replace(",", "-").replace("，", "-")


def official_timeline(data: dict) -> list[dict]:
    """Transpose the official vaccine matrix into an age-first timeline."""
    slot_rows = {
        slot: {"age": label, "slot": slot, "exam": "", "free": [], "paid": [], "price": "", "disease": ""}
        for slot, label in data["columns"]
    }
    diseases: dict[str, list[str]] = {slot: [] for slot in slot_rows}
    for program in data["programs"]:
        for slot, dose in program.get("national", {}).items():
            if slot not in slot_rows:
                continue
            suffix = f"第{dose_text(dose)}剂"
            item = {
                "id": f"official:{program['vax']}:{slot}:{dose_text(dose)}",
                "label": f"{program['name']}（{suffix}）",
                "vax": program["vax"],
                "dose": str(dose),
                "source": "official_reference",
            }
            slot_rows[slot]["free"].append(item)
            if program["disease"] not in diseases[slot]:
                diseases[slot].append(program["disease"])
            if program.get("branch"):
                branch = program["branch"]
                if branch not in diseases[slot]:
                    diseases[slot].append(branch)
            if program.get("audience") and program["audience"] not in diseases[slot]:
                diseases[slot].append(program["audience"])
    for slot, values in diseases.items():
        slot_rows[slot]["disease"] = "；".join(values)
    return [slot_rows[slot] for slot, _ in data["columns"] if slot_rows[slot]["free"]]


def normalize(payload: dict) -> tuple[dict, list[str]]:
    data = copy.deepcopy(payload)
    warnings: list[str] = []
    # 下一站选择固定由模型在最终文字中回复，不进入图片中间件。
    data.pop("next_visit", None)
    data.setdefault("schema_version", "1.0")
    data.setdefault("report", {})
    data["report"].setdefault("id", "vaccine-report")
    data["report"].setdefault("source_completeness", "partial")
    data["report"].setdefault(
        "notice",
        "本图依据本轮列出的官方来源整理，不是儿童个体预约；当地供应和个人适种情况以接种门诊核实为准。",
    )
    has_material_timeline = bool(data.get("timeline"))
    data["report"].setdefault("views", ["time", "vaccine"] if has_material_timeline else ["vaccine"])
    if not data.get("columns") or not data.get("programs"):
        raise ValueError("输入必须包含本轮联网核对后的 columns 和 programs；本 Skill 不再使用包内医学缓存。")
    if not data.get("timeline"):
        data["timeline"] = official_timeline(data)
    data.setdefault("actual_records", [])
    for record in data["actual_records"]:
        if record.get("status") == "administered" and not (
            record.get("item_id") or (record.get("vax") and record.get("dose"))
        ):
            warnings.append("一条已接种记录缺少可匹配的疫苗和剂次，页面未自动标绿。")
    return data, warnings


def record_key(record: dict) -> str:
    return record.get("item_id") or f"{record.get('vax', '')}:{record.get('dose', '')}"


def dose_values(value: object) -> set[str]:
    """Return the individual dose numbers represented by one schedule cell."""
    return {part for part in re.split(r"[\s、,，/\-]+", str(value or "")) if part}


def administered_keys(records: list[dict]) -> set[str]:
    keys: set[str] = set()
    for record in records:
        if record.get("status") != "administered":
            continue
        if record.get("item_id"):
            keys.add(str(record["item_id"]))
        if record.get("vax") and record.get("dose") is not None:
            for dose in dose_values(record.get("dose")):
                keys.add(f"{record['vax']}:{dose}")
    return keys


def vaccine_row_status(program: dict, done: set[str]) -> str:
    """Classify one vaccine row as complete, in progress, or not started."""
    vax = str(program.get("vax") or "")
    expected = {
        dose
        for value in (program.get("national") or {}).values()
        for dose in dose_values(value)
    }
    received = {key.split(":", 1)[1] for key in done if vax and key.startswith(f"{vax}:")}
    if expected and expected.issubset(received):
        return "status-complete"
    if received:
        return "status-progress"
    return "status-not-started"


def render_item(item: dict, kind: str, done: set[str]) -> str:
    item_id = item.get("id", "")
    key = f"{item.get('vax', '')}:{item.get('dose', '')}"
    classes = ["item"]
    if kind == "paid":
        classes.append("paid")
    if item_id in done or key in done:
        classes.append("done")
    return (
        f'<button class="{" ".join(classes)}" data-id="{esc(item_id)}" '
        f'aria-pressed="{str("done" in classes).lower()}">{esc(item.get("label", ""))}</button>'
    )


def render_time_table(data: dict, done: set[str]) -> str:
    body: list[str] = []
    for row in data.get("timeline", []):
        free = "".join(render_item(item, "free", done) for item in row.get("free", []))
        paid = "".join(render_item(item, "paid", done) for item in row.get("paid", []))
        exam = f'<span class="exam-tag">{esc(row.get("exam"))}</span>' if row.get("exam") else ""
        body.append(
            "<tr>"
            f'<td class="age">{esc(row.get("age"))}</td><td class="exam">{exam}</td>'
            f"<td>{free}</td><td>{paid}</td><td class=\"price\">{esc(row.get('price'))}</td>"
            f"<td>{esc(row.get('disease') or row.get('note'))}</td></tr>"
        )
    return (
        '<thead><tr><th class="age" rowspan="2">参考年龄</th><th class="exam" rowspan="2">健康管理</th>'
        '<th class="free" rowspan="2">免疫规划疫苗（免费）</th><th colspan="2">非免疫规划疫苗（自费自愿）</th>'
        '<th rowspan="2">疫苗所预防的疾病／说明</th></tr><tr><th class="paid">非免疫规划疫苗名称</th>'
        '<th class="price">参考价格<br>（以当地门诊为准）</th></tr></thead><tbody>'
        + "".join(body)
        + "</tbody>"
    )


def dose_equal(left: object, right: object) -> bool:
    strip = lambda value: "".join(ch for ch in str(value or "") if ch not in "、,， \t\r\n")
    return strip(left) == strip(right)


def render_matrix_table(data: dict, done: set[str]) -> str:
    columns = data.get("columns", [])
    all_items: list[dict] = []
    for row in data.get("timeline", []):
        for kind in ("free", "paid"):
            for item in row.get(kind, []):
                all_items.append({**item, "kind": kind, "slot": row.get("slot")})
    body: list[str] = []
    for program in data.get("programs", []):
        sources = [item for item in all_items if item.get("vax") == program.get("vax")]
        branch = f'<small><br>{esc(program.get("branch"))}</small>' if program.get("branch") else ""
        cells = [
            f'<td class="disease">{esc(program.get("disease"))}</td>',
            f'<td class="name">{esc(program.get("name"))}{branch}</td>',
            f'<td>{esc(program.get("route"))}</td>',
            f'<td>{esc(program.get("volume"))}</td>',
            f'<td>{esc(program.get("code"))}</td>',
        ]
        for slot, _label in columns:
            national = (program.get("national") or {}).get(slot)
            events = [item for item in sources if item.get("slot") == slot]
            marks: list[str] = []
            if events:
                for item in events:
                    conflict = not national or not dose_equal(national, item.get("dose"))
                    classes = ["source-mark"]
                    if item.get("kind") == "paid":
                        classes.append("paid")
                    if conflict:
                        classes.append("conflict")
                    key = f"{item.get('vax', '')}:{item.get('dose', '')}"
                    if item.get("id") in done or key in done:
                        classes.append("done")
                    note = '<span class="note">（通知单时间）</span>' if conflict else ""
                    marks.append(
                        f'<button class="{" ".join(classes)}" data-id="{esc(item.get("id"))}">'
                        f'<span class="dose">{esc(item.get("dose") or "材")}</span>{note}</button>'
                    )
            elif national:
                moved = any(item.get("slot") != slot and dose_equal(item.get("dose"), national) for item in sources)
                note = '<span class="national-note">（国家建议时间）</span>' if moved else ""
                marks.append(f'<span class="national">{esc(national)}</span>{note}')
            cells.append(f"<td>{''.join(marks)}</td>")
        body.append(f'<tr class="{vaccine_row_status(program, done)}">' + "".join(cells) + "</tr>")
    header = (
        '<thead><tr><th class="disease">可预防疾病</th><th class="name">疫苗种类</th>'
        '<th class="route">接种途径</th><th class="volume">剂量</th><th class="code">英文缩写</th>'
        + "".join(f'<th class="slot">{esc(label)}</th>' for _slot, label in columns)
        + "</tr></thead>"
    )
    return header + "<tbody>" + "".join(body) + "</tbody>"


def render_sources(data: dict) -> str:
    report = data.get("report", {})
    parts = [f"来源：{esc(report.get('source_label') or '用户上传材料')}"]
    if report.get("program_version"):
        parts.append(f"程序版次：{esc(report['program_version'])}")
    if report.get("published_at"):
        parts.append(f"发布日期：{esc(report['published_at'])}")
    if report.get("verified_at"):
        parts.append(f"本轮核对：{esc(report['verified_at'])}")
    links = []
    for source in data.get("sources", []):
        if source.get("url"):
            links.append(f'<a href="{esc(source["url"])}" rel="noreferrer">{esc(source.get("title") or source["url"])}</a>')
    return "；".join(parts) + (("<br>官方依据：" + "；".join(links)) if links else "")


def screenshot(html_path: Path, output_path: Path, view: str) -> None:
    try:
        from render_vaccine_png import render
    except Exception as exc:
        raise RuntimeError(
            "无浏览器渲染依赖不可用；需要 weasyprint==70.0、"
            "pymupdf==1.28.2、Pango/Cairo 和中文字体。"
        ) from exc
    render(html_path, view, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="符合 image-output.md 的 JSON")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", default="儿童疫苗接种双视图")
    parser.add_argument("--no-screenshots", action="store_true")
    args = parser.parse_args()

    payload = load_json(args.input.resolve())
    data, warnings = normalize(payload)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    template = (ASSETS / "image-template.html").read_text(encoding="utf-8")
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    report = data.get("report", {})
    views = report.get("views") or ["vaccine"]
    done = administered_keys(data.get("actual_records", []))
    if len(views) == 1:
        selector = ""
        time_class = "time-view single-visible" if views[0] == "time" else "time-view"
        vaccine_class = "vaccine-view single-visible" if views[0] == "vaccine" else "vaccine-view"
    else:
        selector = (
            '<input class="view-radio" type="radio" name="report-view" id="view-time" checked>'
            '<input class="view-radio" type="radio" name="report-view" id="view-vaccine">'
            '<nav class="toolbar" aria-label="查看方式" role="tablist"><div class="tabs">'
            '<label for="view-time" role="tab">按时间看</label>'
            '<label for="view-vaccine" role="tab">按疫苗看</label></div></nav>'
        )
        time_class = "time-view"
        vaccine_class = "vaccine-view"
    source_html = render_sources(data)
    if len(views) == 1 and views[0] == "vaccine":
        vaccine_legend = (
            '<span><i class="gray"></i>国家免疫程序参考剂次</span>'
            '<span><i class="complete-row"></i>整行绿色：该疫苗全程已完成</span>'
            '<span><i class="progress-row"></i>整行蓝色：已接种部分剂次</span>'
            '<span><i class="pending-row"></i>原色：尚无已接种记录</span>'
        )
    else:
        vaccine_legend = (
            '<span><i class="black"></i>上传材料安排</span><span><i class="gray"></i>国家参考</span>'
            '<span><i class="red"></i>两套时间不同</span>'
            '<span><i class="complete-row"></i>整行绿色：全程已完成</span>'
            '<span><i class="progress-row"></i>整行蓝色：已接种部分剂次</span>'
        )
    replacements = {
        "__REPORT_DATA__": embedded,
        "__VIEW_SELECTOR__": selector,
        "__TIME_SECTION_CLASS__": time_class,
        "__VACCINE_SECTION_CLASS__": vaccine_class,
        "__TIME_TITLE__": esc(report.get("title_time") or "体检、疫苗接种预约告知单"),
        "__TIME_SUBTITLE__": esc(report.get("subtitle_time") or ""),
        "__VACCINE_TITLE__": esc(report.get("title_vaccine") or "国家免疫规划疫苗儿童免疫程序表"),
        "__VACCINE_SUBTITLE__": esc(report.get("subtitle_vaccine") or ""),
        "__NOTICE__": esc(report.get("notice") or ""),
        "__TIME_TABLE__": render_time_table(data, done),
        "__MATRIX_TABLE__": render_matrix_table(data, done),
        "__VACCINE_LEGEND__": vaccine_legend,
        "__SOURCE_HTML__": source_html,
        "__PAGE_TITLE__": esc(
            report.get("title_vaccine") if len(views) == 1 and views[0] == "vaccine"
            else report.get("title_time") or "儿童疫苗接种整理"
        ),
    }
    html = template
    for needle, value in replacements.items():
        html = html.replace(needle, value)
    html_path = args.output_dir / f"{args.name}.html"
    html_path.write_text(html, encoding="utf-8")
    outputs = {"html": str(html_path.resolve())}
    invalid_views = set(views) - {"time", "vaccine"}
    if invalid_views:
        raise ValueError(f"不支持的视图: {sorted(invalid_views)}")
    if not args.no_screenshots:
        for view, suffix in (("time", "按时间"), ("vaccine", "按疫苗")):
            png = args.output_dir / f"{args.name}-{suffix}.png"
            if view not in views:
                if png.exists():
                    png.unlink()
                continue
            screenshot(html_path, png, view)
            outputs[view] = str(png.resolve())
    manifest = {
        "schema_version": data["schema_version"],
        "source_mode": data["report"].get("source_mode", "material"),
        "source_completeness": data["report"].get("source_completeness", "partial"),
        "views": views,
        "warnings": warnings,
        "outputs": outputs,
    }
    manifest_path = args.output_dir / f"{args.name}-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**manifest, "manifest": str(manifest_path.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
