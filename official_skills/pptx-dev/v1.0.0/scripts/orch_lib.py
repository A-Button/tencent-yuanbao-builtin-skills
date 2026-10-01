#!/usr/bin/env python3
"""编排层进程内调用封装：用 import 替代 subprocess，并隔离异常/SystemExit/stdio。

设计目标：
- 编排器（apply_plan / finalize_run）不再为每个步骤起 Python 子进程；
- 子模块的异常、sys.exit、stdout/stderr 打印不影响编排进程继续与其它步骤；
- 各脚本仍可独立 CLI 运行；本模块只多一层可 import 的安全胶水。
"""

from __future__ import annotations

import io
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

# 保证同目录脚本可互相 import（镜像内 /data/skills/pptx/scripts）
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_OFFICE = _SCRIPTS / 'office'
if str(_OFFICE) not in sys.path:
    sys.path.insert(0, str(_OFFICE))


@dataclass
class Result:
    """兼容旧 subprocess.CompletedProcess 的最小字段，并可选携带结构化 data。"""
    returncode: int = 0
    stdout: str = ''
    stderr: str = ''
    data: Any = None
    error: str | None = None


def _system_exit_code(exc: BaseException) -> tuple[int, str]:
    """把 SystemExit 归一成 (returncode, stderr_extra)。sys.exit('msg') 的 code 是 str。"""
    code = getattr(exc, 'code', 1)
    if code is None:
        return 0, ''
    if isinstance(code, int):
        return code, ''
    return 1, str(code)


def safe_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Result:
    """在隔离的 stdout/stderr 下调用 fn；吞掉 Exception/SystemExit，绝不向外抛。"""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            ret = fn(*args, **kwargs)
    except SystemExit as exc:
        rc, extra = _system_exit_code(exc)
        if extra:
            err_buf.write(extra if extra.endswith('\n') else extra + '\n')
        return Result(returncode=rc, stdout=out_buf.getvalue(), stderr=err_buf.getvalue(),
                      error=extra or None)
    except BaseException as exc:  # noqa: BLE001 — 编排层必须吞掉，避免拖垮其它步骤
        # KeyboardInterrupt/SystemExit 已在上面；其余含 Exception
        if isinstance(exc, (KeyboardInterrupt, GeneratorExit)):
            raise
        err_buf.write(f'{type(exc).__name__}: {exc}\n')
        err_buf.write(traceback.format_exc()[-800:])
        return Result(returncode=1, stdout=out_buf.getvalue(), stderr=err_buf.getvalue(),
                      error=f'{type(exc).__name__}: {exc}')

    stdout, stderr = out_buf.getvalue(), err_buf.getvalue()
    if isinstance(ret, Result):
        # 内层已是 Result：合并被重定向捕获的打印
        ret.stdout = (ret.stdout or '') + stdout
        ret.stderr = (ret.stderr or '') + stderr
        return ret
    if isinstance(ret, int):
        return Result(returncode=ret, stdout=stdout, stderr=stderr)
    if isinstance(ret, tuple) and len(ret) == 2 and isinstance(ret[0], int):
        code, data = ret
        return Result(returncode=code, stdout=stdout, stderr=stderr, data=data)
    return Result(returncode=0, stdout=stdout, stderr=stderr, data=ret)


def run_parallel(named: list[tuple[str, Callable[[], Result]]]) -> dict[str, Result]:
    """并行跑互不依赖的步骤；每步已是 safe_call 结果，互不影响。"""
    if not named:
        return {}
    if len(named) == 1:
        name, fn = named[0]
        return {name: fn()}
    out: dict[str, Result] = {}
    with ThreadPoolExecutor(max_workers=len(named)) as pool:
        futs = {pool.submit(fn): name for name, fn in named}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                out[name] = fut.result()
            except BaseException as exc:  # noqa: BLE001
                if isinstance(exc, (KeyboardInterrupt, GeneratorExit)):
                    raise
                out[name] = Result(returncode=1, stderr=f'{type(exc).__name__}: {exc}',
                                   error=str(exc))
    return out


# ── 各步骤的 import 调用（失败只返回 Result，不抛给编排器）──────────────────

def plan_from_lines(deck_path: Path, lines_path: Path) -> Result:
    def _go():
        import plan_from_lines as m
        plan = m.build_plan(deck_path, lines_path)
        text = json.dumps(plan, ensure_ascii=False, indent=2)
        return Result(returncode=0, stdout=text, data=plan)

    return safe_call(_go)


def replace_text(unpacked: Path, plan_path: Path, report_path: Path | None = None,
                 quiet: bool = True) -> Result:
    def _go():
        import replace_text as m
        code, report = m.run(unpacked, plan_path, report_path=report_path, quiet=quiet)
        return Result(returncode=code, data=report)

    return safe_call(_go)


def replace_image_set(unpacked: Path, slide: int, image: str,
                      index: int | None = None, visual_index: int | None = None) -> Result:
    def _go():
        import replace_image as m
        args = SimpleNamespace(
            unpacked=str(unpacked),
            slide=slide,
            index=index,
            visual_index=visual_index,
            image=image,
            fit='cover',
            dpi=150,
            max_edge=2000,
            quality=82,
            no_optimize=False,
        )
        return m.cmd_set(args)

    return safe_call(_go)


def replace_images_batch(
    unpacked: Path,
    jobs: list[dict],
    *,
    max_workers: int = 8,
) -> list[Result]:
    """并行替换多张图；jobs 顺序与返回 Result 列表一致。

    每个 job: {slide, image, index?, visual_index?}。
    同页由 replace_image 内 slide_lock 串行；不同页并行。
    """
    if not jobs:
        return []
    if len(jobs) == 1:
        j = jobs[0]
        return [replace_image_set(
            unpacked, slide=int(j['slide']), image=str(j['image']),
            index=j.get('index'), visual_index=j.get('visual_index'),
        )]

    results: list[Result | None] = [None] * len(jobs)
    workers = min(max_workers, len(jobs))

    def _one(idx: int, job: dict) -> tuple[int, Result]:
        return idx, replace_image_set(
            unpacked, slide=int(job['slide']), image=str(job['image']),
            index=job.get('index'), visual_index=job.get('visual_index'),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, i, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                _, res = fut.result()
            except BaseException as exc:  # noqa: BLE001
                if isinstance(exc, (KeyboardInterrupt, GeneratorExit)):
                    raise
                res = Result(returncode=1, error=f'{type(exc).__name__}: {exc}')
            results[idx] = res
    return [r if r is not None else Result(returncode=1, error='missing') for r in results]


def edit_chart(unpacked: Path, charts_path: Path, report_path: Path | None = None) -> Result:
    def _go():
        import edit_chart as m
        ops = json.loads(charts_path.read_text(encoding='utf-8'))
        if not isinstance(ops, list):
            raise ValueError('charts.json 必须是 JSON 数组')
        report = m.apply_ops(unpacked, ops)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('errors') else 0, stdout=text, data=report)

    return safe_call(_go)


def edit_table(unpacked: Path, tables_path: Path, report_path: Path | None = None) -> Result:
    def _go():
        import edit_table as m
        ops = json.loads(tables_path.read_text(encoding='utf-8'))
        if not isinstance(ops, list):
            raise ValueError('tables.json 必须是 JSON 数组')
        report = m.apply_ops(unpacked, ops)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('errors') else 0, stdout=text, data=report)

    return safe_call(_go)


def adjust_shape(unpacked: Path, layout_path: Path, report_path: Path | None = None) -> Result:
    def _go():
        import adjust_shape as m
        ops = json.loads(layout_path.read_text(encoding='utf-8'))
        if not isinstance(ops, list):
            raise ValueError('layout ops 必须是 JSON 数组')
        report = m.apply_ops(unpacked, ops)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('errors') else 0, stdout=text, data=report)

    return safe_call(_go)


def set_notes(unpacked: Path, notes_path: Path, report_path: Path | None = None,
              quiet: bool = True) -> Result:
    def _go():
        import set_notes as m
        code, result = m.run(unpacked, str(notes_path), report_path=report_path, quiet=quiet)
        return Result(returncode=code, data=result)

    return safe_call(_go)


def pack_pptx(unpacked: Path, output: Path, original: str | None = None) -> Result:
    def _go():
        from pack import pack as pack_fn
        _, message = pack_fn(str(unpacked), str(output), original_file=original, validate=True)
        rc = 1 if message and 'Error' in message else 0
        return Result(returncode=rc, stdout=message or '', stderr='' if rc == 0 else (message or ''))

    return safe_call(_go)


def verify_content(unpacked: Path, deck: Path, plan: Path, report_path: Path | None = None,
                   scope: set[int] | None = None) -> Result:
    def _go():
        import verify_content as m
        report = m.verify(unpacked, deck, plan, scope=scope)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('blocking_count') else 0, stdout=text, data=report)

    return safe_call(_go)


def check_layout(pptx: Path, baseline_template: str | None = None) -> Result:
    def _go():
        import check_layout as m
        report = m.check_pptx(str(pptx), baseline_template=baseline_template)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        return Result(returncode=2 if report.get('blocking_count') else 0, stdout=text, data=report)

    return safe_call(_go)


def check_images(pptx: Path, template: str, report_path: Path | None = None) -> Result:
    def _go():
        import check_images as m
        report = m.check(str(pptx), template, 0.02)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('blocking_count') else 0, stdout=text, data=report)

    return safe_call(_go)


def check_contrast(pptx: Path, baseline_template: str | None = None,
                   report_path: Path | None = None) -> Result:
    def _go():
        import check_contrast as m
        report = m.check_with_baseline(str(pptx), baseline_template)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('blocking_count') else 0, stdout=text, data=report)

    return safe_call(_go)


def validate_pptx(pptx: Path, report_path: Path | None = None) -> Result:
    def _go():
        import validate_pptx as m
        report = m.validate(str(pptx), render=False)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('blocking_count') else 0, stdout=text, data=report)

    return safe_call(_go)


def check_charts(pptx: Path, template: str, report_path: Path | None = None) -> Result:
    def _go():
        import check_charts as m
        report = m.check(str(pptx), template)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('blocking_count') else 0, stdout=text, data=report)

    return safe_call(_go)


def check_tables(pptx: Path, template: str, report_path: Path | None = None) -> Result:
    def _go():
        import check_tables as m
        report = m.check(str(pptx), template)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=2 if report.get('blocking_count') else 0, stdout=text, data=report)

    return safe_call(_go)


def check_structure(pptx: Path, report_path: Path | None = None) -> Result:
    def _go():
        import check_structure as m
        report = m.check(str(pptx))
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if report_path:
            report_path.write_text(text, encoding='utf-8')
        return Result(returncode=0, stdout=text, data=report)

    return safe_call(_go)


def optimize_media_inplace(pptx: Path, max_edge: int = 1600, quality: int = 80) -> Result:
    def _go():
        import optimize_template_media as m
        tmp = pptx.with_suffix('.slimtmp.pptx')
        report = m.optimize_pptx(pptx, tmp, max_edge, quality)
        tmp.replace(pptx)
        report['dst'] = str(pptx)
        msg = (f"media {report['media_before']/1e6:.1f}MB -> {report['media_after']/1e6:.1f}MB "
               f"(reencoded={report['reencoded']}, dropped={report['dropped_orphans']})")
        return Result(returncode=0, stdout=msg, data=report)

    return safe_call(_go)


def embed_fonts_inplace(pptx: Path) -> Result:
    def _go():
        import embed_fonts as m
        dst = pptx.with_suffix('.embedtmp.pptx')
        try:
            rep = m.embed(pptx, dst)
        except Exception as e:  # noqa: BLE001 — 与 CLI 一致：失败不阻断
            if dst.exists():
                dst.unlink()
            return Result(returncode=0, stdout=json.dumps(
                {'ok': False, 'reason': f'{type(e).__name__}: {e}'}, ensure_ascii=False))
        if not rep.get('ok'):
            if dst.exists():
                dst.unlink()
            return Result(returncode=0, stdout=json.dumps(rep, ensure_ascii=False), data=rep)
        dst.replace(pptx)
        return Result(returncode=0, stdout=json.dumps(rep, ensure_ascii=False), data=rep)

    return safe_call(_go)


def normalize_ooxml(pptx: Path) -> Result:
    def _go():
        from ooxml_ns import normalize_pptx, fix_paragraph_order, deshare_owned_parts
        ns_rep = normalize_pptx(pptx)
        po_rep = fix_paragraph_order(pptx)
        ds_rep = deshare_owned_parts(pptx)
        data = {'ns': ns_rep, 'para_order': po_rep, 'deshare': ds_rep}
        return Result(returncode=0, stdout=json.dumps(data, ensure_ascii=False)[:500], data=data)

    return safe_call(_go)
