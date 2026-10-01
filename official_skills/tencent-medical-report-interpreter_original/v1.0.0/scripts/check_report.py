#!/usr/bin/env python3
"""
报告合规校验工具（check_report.py）

用途：对生成的 HTML 报告做机器可检的合规校验，覆盖「七条硬性要求」、
      结构与命名、表格一致性，以及质量保障要求里的措辞禁止清单。
      生成报告后应跑一遍再交付。

为什么需要：
  有些错误肉眼看不出来但会破坏阅读 —— 典型是表格加列后漏改某一行，
  渲染时整行错位；还有目录锚点失效、章节断号、CDN 残留。
  措辞类违规（绝对化表述、给剂量疗程、质疑医院）同样靠人眼容易漏，
  且属医疗合规风险，必须机器兜底。
  这些用正则一扫即知，不该靠人眼。

用法：
  python3 check_report.py <报告.html>
  python3 check_report.py <报告.html> --quiet     # 只输出失败项

选项：
  --quiet      只输出失败项
  --template   模板模式：跳过「目录导航」与「参考指南段」两项内容完整性校验。
               模板（templates/report_template.html）是骨架，本就不含填好的目录与
               指南表，按成品标准校验必然 2 项失败 —— 那是误报，不是模板坏了。

关于「27 项」：本文件有 25 个 check_* 方法，但 check_sections 与 check_toc
             各输出 2 项（序号 + 标题；锚点 + 目录文字），故成品报告共 27 项。
             改动检查项后请同步 SKILL.md 与 README 里的项数。

退出码：
  0 = 全部通过    1 = 存在不合规项

参考完整示例：examples/sample_report.html
"""

import argparse
import os
import re
import sys

EXPECTED_TITLES = [
    "报告总结", "处理优先级", "异常指标详细解读", "关联性分析",
    "干扰因素排查", "风险预测", "趋势变化", "下一步",
    "生活指导", "参考指南", "重要提醒",
]

# 不该出现在成品报告里的词
DEV_TRACES = ["示例", "模板", "TODO", "占位", "待评审", "方案 v2", "demo", "FIXME"]

# 身份信息字段
PRIVACY_FIELDS = ["身份证", "手机号", "姓名：", "门诊号", "住院号", "病案号"]

# 否定语境：免责声明里写「本报告不含姓名、门诊号」属于合规声明，不是泄漏。
# 纯关键词匹配会把这种声明误判为违规，排查时极具误导性。
PRIVACY_NEGATORS = [
    "不含", "不包含", "未包含", "无", "不采集", "不留存", "不涉及",
    "已脱敏", "已隐去", "已移除", "不索取", "不显示", "不记录",
]

# ── 属性容忍的标签片段 ────────────────────────────────────
# 不能把标签写成 <span class="no"> 这种「不带其他属性」的死形态：
# HTML 只要经过预览面板、编辑器或任何序列化工具，就会被注入
# data-* 之类属性（实测预览会加 data-page-node-id），导致全部正则失配，
# 校验器反过来报「未找到目录」「序号异常：[]」，把排查方向彻底带偏。
def _tag(name, cls=None):
    """生成容忍任意额外属性、且 class 可含其他类名的标签开头模式。"""
    if cls is None:
        return r"<%s\b[^>]*>" % name
    return r'<%s\b[^>]*class="[^"]*\b%s\b[^"]*"[^>]*>' % (name, cls)


SPAN_NO = _tag("span", "no")
SPAN_TTL = _tag("span", "ttl")
SPAN_ANY = _tag("span")
DIV_DH = _tag("div", "dh")
# 段号 + 段名：两个 span 之间允许有空白
SEC_TITLE_RE = SPAN_NO + r"\s*(\d+)\s*</span>\s*" + SPAN_TTL + r"(.*?)</span>"
DISC_TITLE_RE = DIV_DH + r"\s*" + SPAN_NO + r"\s*(\d+)\s*</span>\s*" + SPAN_ANY + r"(.*?)</span>"
TOC_LINK_RE = r'<a\b[^>]*href="#(s\d+)"[^>]*>\s*<b\b[^>]*>\s*(\d+)\s*</b>(.*?)</a>'

# 已废弃的口语化/内部术语标题
BAD_TITLES = [
    "先看这里", "哪些要紧", "每项指标什么意思", "几项异常放在一起",
    "虚惊一场", "风险算给你看", "和以前比", "接下来该做什么",
    "吃动睡", "交叉模式发现", "异常指标综合分析", "定量风险评估",
]

# 不该暴露给用户的内部档位代号
LEVEL_CODES = r"L[1-4]\s*档|按\s*L[1-4]|档位[：:]\s*L[1-4]|>L[1-4]<"

# ── 质量保障：禁止表述（对应 SKILL.md 质量保障要求 A/B 两组）────────────
#
# 全部为「排除已知合法用法后」的收紧写法，避免误判：
#   绝对值 / 绝对变化  → 中性粒细胞绝对值是规范术语，必须放行
#   mg/dL、mg/L        → 是检验单位，不是药物剂量
#   一定程度上          → 程度副词，非绝对化断言
#   一定要带报告         → 就诊准备的强调语，非医疗断言
#   不能肯定 / 无法肯定  → 恰恰是谨慎表述，必须放行

# B5 绝对化表述
ABSOLUTE_WORDS = [
    (r"(?<![不无未难])(?<!不能)(?<!无法)(?<!难以)肯定", "肯定"),
    (r"一定(?![程要])", "一定"),
    (r"必然", "必然"),
    (r"必定", "必定"),
    (r"百分百|百分之百", "百分百"),
    (r"绝对(?!值)(?!变化)(?!数)", "绝对"),
    (r"毫无疑问|无疑是|确凿无疑", "无疑"),
    (r"绝症", "绝症"),
    (r"治不好|没救|无药可治", "治不好"),
    (r"完全没问题|完全没事|完全健康", "完全没问题"),
]

# B3 说无需治疗
NO_TREATMENT_WORDS = [
    r"不需要治疗", r"无需治疗", r"不用治疗", r"不必治疗",
    r"不用吃药", r"不需吃药", r"无需服药", r"不用服药",
    r"不用管", r"无需处理", r"不必处理", r"不用复查", r"无需复查",
]

# B4 用药剂量与疗程
DOSAGE_PATTERNS = [
    (r"\d+(?:\.\d+)?\s*(?:mg|毫克|μg|ug|微克|IU|国际单位)(?![/a-zA-Z])", "药物剂量"),
    (r"\d+\s*(?:片|粒|袋|支|胶囊)\b", "药物剂量"),
    (r"每[日天]\s*\d+\s*(?:次|片|粒)", "用药频次"),
    (r"\b(?:qd|bid|tid|qid|q\dh)\b", "用药频次缩写"),
    (r"疗程", "疗程"),
    (r"连(?:服|用|吃)\s*\d+", "疗程"),
    (r"(?:服|吃)\s*\d+\s*(?:周|个月|月|天)", "疗程"),
]

# B6 医疗纠纷相关表述
DISPUTE_WORDS = [
    r"检测有误", r"检验有误", r"化验有误", r"结果不准", r"结果有误",
    r"报告写错", r"报告错了", r"化验错了", r"医院搞错", r"医院弄错",
    r"医院水平", r"换(?:家|一家|个|一个)医院", r"这家医院不",
    r"设备有问题", r"仪器不准", r"医生看错",
]

# A3 歧义表述（必须落到具体指标与数值）
AMBIGUOUS_WORDS = [
    r"血脂高(?![于])", r"肝功能不好", r"肾不好", r"肾功能不好",
    r"内分泌失调", r"血象异常", r"三高(?!危)",
]

# 不得出现在交付物里的本机路径
LOCAL_PATHS = [
    (r"/Users/[A-Za-z0-9._-]+", "macOS 用户目录"),
    (r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9._-]+", "Windows 用户目录"),
    (r"/home/[A-Za-z0-9._-]+", "Linux 用户目录"),
    (r"versions/\d+\.\d[\d.]*/bin", "带版本号的解释器路径"),
    (r"/tmp/[A-Za-z0-9_-]", "临时目录"),
    (r"/var/folders/[A-Za-z0-9]", "临时目录"),
]


# ── 内部机制名：只有开发者会用的词，绝不能出现在交付物里 ────────────
#
# 与 LEVEL_CODES 同一原则（内部推理不出现在交付物），但覆盖面更广。
# 2026-09-20 实战触发：输出前言里出现「可以按 skill 流程判读」
# 「已跑危急值闸门：未命中」「判读链在此没有可作用的对象」「无法产出 11 段解读」。
#
# 收紧说明（避免误判医学正文）：
#   「危急值」单独出现是规范医学术语，必须放行；只拦「危急值闸门」这个内部流程名。
#   「段」「档」单独出现常见于正文，只拦带数字或内部档名的组合。
#   「我」单独出现不拦，只拦明确的元话语句式。
INTERNAL_TERMS = [
    (r"\bskill\b", "工具自称 skill"),
    (r"本技能|技能包", "工具自称"),
    (r"危急值闸门|判读链|解读链|问题层归纳|交叉模式库?|陷阱表", "内部流程名"),
    (r"快查卡|模式库", "内部资料名"),
    (r"\d+\s*段解读|段数上限|字数上限", "内部规模控制"),
    (r"速读档|标准档|完整档|档\s*[ABC](?![a-zA-Z])", "内部档位名"),
    (r"已跑(?:完)?(?:危急值|陷阱|模式)", "步骤执行汇报"),
    (r"已加载|按\s*Steps|走了第.步", "步骤执行汇报"),
    (r"我不这样做|我不会这样做|让我先|我先跑|我判断|我决定", "第一人称元话语"),
]

class Checker:
    def __init__(self, path, quiet=False, template=False):
        self.path = path
        self.quiet = quiet
        # 模板模式：骨架文件不含填好的目录与指南表，这两项按成品标准校验属误报
        self.template = template
        self.raw = open(path, encoding="utf-8").read()
        # 去掉 HTML 注释后的可见内容 —— 注释里的示例文本不算违规
        self.body = re.sub(r"<!--.*?-->", "", self.raw, flags=re.S)
        # 再剥掉标签与 style/script，得到纯文本 —— 措辞类校验只看用户读到的字
        txt = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", self.body, flags=re.S | re.I)
        self.text = re.sub(r"<[^>]+>", " ", txt)
        self.failed = []
        self.passed = []

    def ok(self, name, detail=""):
        self.passed.append((name, detail))

    def bad(self, name, detail):
        self.failed.append((name, detail))

    # ── 七条硬性要求 ──────────────────────────────────────
    def check_no_external(self):
        urls = [
            u for u in re.findall(r'(?:src|href)=["\'](https?://[^"\']+)', self.raw)
            if "w3.org" not in u
        ]
        if urls:
            self.bad("零外部依赖", f"发现 {len(urls)} 个外链：{urls[:3]}")
        else:
            self.ok("零外部依赖")

    def check_no_script(self):
        n = len(re.findall(r"<script", self.body, re.I))
        if n:
            self.bad("零 script", f"发现 {n} 个 script 标签")
        else:
            self.ok("零 script")

    def check_inline_svg(self):
        has_trend = "趋势变化" in self.body
        if not has_trend:
            self.ok("内联 SVG 趋势图", "单份报告，无趋势段（跳过）")
            return
        if re.search(r"<polyline", self.body):
            self.ok("内联 SVG 趋势图")
        else:
            self.bad("内联 SVG 趋势图", "有趋势段但未找到 polyline，图表可能缺失")

    def check_color_scheme(self):
        if re.search(r'name=["\']color-scheme["\'][^>]*light', self.raw):
            self.ok("锁定浅色模式")
        else:
            self.bad("锁定浅色模式",
                     '缺 <meta name="color-scheme" content="light">，'
                     "手机深色模式会反色")

    def check_table_wrap(self):
        tables = len(re.findall(r"<table[^>]*>", self.body))
        wraps = len(re.findall(r'class="tw"', self.body))
        if tables == 0:
            self.ok("表格可横滑", "无表格")
        elif tables == wraps:
            self.ok("表格可横滑", f"{tables} 个表格全部包裹")
        else:
            self.bad("表格可横滑", f"{tables} 个表格但只有 {wraps} 个 .tw 容器")

    def check_no_dev_traces(self):
        found = [w for w in DEV_TRACES if w.lower() in self.body.lower()]
        if found:
            self.bad("无开发痕迹", f"发现：{found}")
        else:
            self.ok("无开发痕迹")

    def check_no_privacy(self):
        found = []
        for w in PRIVACY_FIELDS:
            for m in re.finditer(re.escape(w), self.body):
                # 往前看 16 字，命中否定词则视为合规声明而非泄漏
                ctx = self.body[max(0, m.start() - 16):m.start()]
                if any(n in ctx for n in PRIVACY_NEGATORS):
                    continue
                found.append(w)
                break
        if found:
            self.bad("无身份信息", f"发现：{found}")
        else:
            self.ok("无身份信息")

    # ── 结构与命名 ────────────────────────────────────────
    def check_sections(self):
        secs = re.findall(SEC_TITLE_RE, self.body, re.S)
        disc = re.search(DISC_TITLE_RE, self.body, re.S)
        found = [(int(n), t.strip()) for n, t in secs]
        if disc:
            found.append((int(disc.group(1)), disc.group(2).strip()))

        nums = [n for n, _ in found]
        titles = [t for _, t in found]

        # 允许单份报告缺 07（趋势），此时序号应为 1-6,8-11
        full = list(range(1, 12))
        no_trend = [n for n in full if n != 7]
        if nums == full:
            self.ok("章节序号", "01~11 完整")
        elif nums == no_trend:
            self.ok("章节序号", "01~11（单份报告，无 07 趋势段）")
        elif not nums:
            self.bad("章节序号",
                     "未识别到任何标准章节标记 —— 若本文件是自定义结构（非 11 段"
                     "标准报告），本项不适用；若应为标准报告，检查 "
                     '<span class="no"> / <span class="ttl"> 是否被改写')
        else:
            self.bad("章节序号", f"序号异常：{nums}")

        expected = {i + 1: t for i, t in enumerate(EXPECTED_TITLES)}
        wrong = [(n, t, expected.get(n)) for n, t in found if expected.get(n) != t]
        if wrong:
            self.bad("章节标题", f"与规范不符：{wrong}")
        elif not titles:
            self.ok("章节标题", "无标准章节标记，跳过")
        else:
            self.ok("章节标题", f"{len(titles)} 段全部符合规范")

    def check_toc(self):
        if self.template:
            self.ok("目录导航", "模板模式，跳过内容完整性校验")
            self.ok("目录文字", "模板模式，跳过内容完整性校验")
            return
        links = re.findall(TOC_LINK_RE, self.body, re.S)
        ids = set(re.findall(r'id="(s\d+)"', self.body))
        if not links:
            self.bad("目录导航", "未找到目录，长报告缺目录只能一路下滑")
            return
        broken = [l[0] for l in links if l[0] not in ids]
        if broken:
            self.bad("目录锚点", f"失效链接：{broken}")
        else:
            self.ok("目录锚点", f"{len(links)} 项全部可跳转")

        # 目录文字须与章节标题一致
        sec_map = {}
        for n, t in re.findall(SEC_TITLE_RE, self.body, re.S):
            sec_map[f"s{n}"] = t.strip()
        d = re.search(DISC_TITLE_RE, self.body, re.S)
        if d:
            sec_map[f"s{d.group(1)}"] = d.group(2).strip()
        # 目录里常写成 <b>1</b> 标题（</b> 后带空格），比对前必须 strip
        mismatch = [
            (l[0], l[2].strip(), sec_map.get(l[0]))
            for l in links
            if l[0] in sec_map and sec_map[l[0]] != l[2].strip()
        ]
        if mismatch:
            self.bad("目录文字", f"与章节标题不一致：{mismatch}")
        elif not sec_map:
            self.ok("目录文字", "无标准章节标记，跳过比对")
        else:
            self.ok("目录文字", "与章节标题一致")

    def check_no_emoji(self):
        emo = [
            c for c in self.body
            if 0x1F300 <= ord(c) <= 0x1FAFF
            or 0x2600 <= ord(c) <= 0x27BF
            or ord(c) == 0xFE0F
        ]
        if emo:
            self.bad("无 emoji", f"发现：{sorted(set(emo))}")
        else:
            self.ok("无 emoji")

    def check_bad_titles(self):
        # 只在标题元素内检测 —— 正文里出现「把几项异常放在一起看」是正常表述，
        # 不能因为字面包含旧标题词就误判
        titles = re.findall(
            SPAN_TTL + r"(.*?)</span>"
            + r"|" + _tag("h3", "sub") + r"(.*?)</h3>"
            + r"|" + _tag("h4", "sub2") + r"(.*?)</h4>",
            self.body, re.S,
        )
        flat = " ".join(t for grp in titles for t in grp if t)
        flat = re.sub(r"<.*?>", "", flat)
        found = [w for w in BAD_TITLES if w in flat]
        if found:
            self.bad("标题调性", f"标题中发现已废弃的口语化/内部术语：{found}")
        else:
            self.ok("标题调性", f"已检查 {len(titles)} 个标题")

    def check_no_level_codes(self):
        found = re.findall(LEVEL_CODES, self.body)
        if found:
            self.bad("档位代号", f"向用户暴露了 L1~L4 内部代号：{sorted(set(found))}")
        else:
            self.ok("档位代号", "未暴露 L1~L4")

    def check_sub_numbering(self):
        n2 = len(re.findall(_tag("span", "n2"), self.body))
        n3 = len(re.findall(_tag("span", "n3"), self.body))
        h3 = len(re.findall(_tag("h3", "sub"), self.body))
        h4 = len(re.findall(_tag("h4", "sub2"), self.body))
        # 原来用 elif，二级与三级同时缺序号时只报前者，修完再跑又冒出新错
        errs = []
        if h3 and n2 != h3:
            errs.append(f"二级 {h3} 个标题但只有 {n2} 个序号")
        if h4 and n3 != h4:
            errs.append(f"三级 {h4} 个标题但只有 {n3} 个序号")
        if errs:
            self.bad("标题序号", "；".join(errs))
        else:
            self.ok("标题序号", f"二级 {n2} 个、三级 {n3} 个，全部带序号")

    @staticmethod
    def _grid_widths(table_html):
        """按渲染网格算每行实际列宽，正确处理 colspan / rowspan。

        只数 <td>/<th> 个数是错的：colspan="2" 的单元格占 2 列却只算 1 个；
        rowspan="2" 会让下一行少一个 <td>，两者都会把合法表格误判为列数不齐。
        """
        widths = []
        pending = []  # [剩余行数, 占用列数]，由 rowspan 向下传递
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
            w = 0
            carry = []
            for rem, cs in pending:
                w += cs
                if rem - 1 > 0:
                    carry.append([rem - 1, cs])
            for attrs in re.findall(r"<t[hd]([^>]*)>", row):
                m = re.search(r'colspan\s*=\s*["\']?(\d+)', attrs)
                cs = int(m.group(1)) if m else 1
                m = re.search(r'rowspan\s*=\s*["\']?(\d+)', attrs)
                rs = int(m.group(1)) if m else 1
                w += cs
                if rs > 1:
                    carry.append([rs - 1, cs])
            pending = carry
            widths.append(w)
        return widths

    def check_table_columns(self):
        bad = []
        # <table 可能带属性，不能只匹配 <table>
        for i, t in enumerate(
            re.findall(r"<table[^>]*>.*?</table>", self.body, re.S), 1
        ):
            cols = self._grid_widths(t)
            if len(set(cols)) > 1:
                bad.append((i, cols))
        if bad:
            self.bad("表格列数一致性",
                     f"{len(bad)} 个表格列数不齐（会导致渲染错位）：{bad[:3]}")
        else:
            n = len(re.findall(r"<table[^>]*>", self.body))
            self.ok("表格列数一致性", f"{n} 个表格全部一致")

    def check_note_budget(self):
        n = len(re.findall(_tag("div", "note"), self.body))
        if n > 5:
            self.bad("色块预算", f"{n} 处底色块，超出 ≤5 的限制，会让重点失效")
        else:
            self.ok("色块预算", f"{n} 处（限 ≤5）")

    def check_guidelines_section(self):
        if self.template:
            self.ok("参考指南段", "模板模式，跳过内容完整性校验")
            return
        # 不能用 id="s10".*?(?=id="s11") —— 一旦第 11 段换了标记方式或被删，
        # 会误报成「未找到第 10 段」，而实际 s10 是存在的，排查方向被带偏。
        start = re.search(r'id="s10"', self.body)
        if not start:
            self.bad("参考指南段", '未找到第 10 段（缺少 id="s10"）')
            return
        tail = self.body[start.end():]
        nxt = re.search(r'id="s\d+"', tail)
        blk = tail[:nxt.start()] if nxt else tail
        rows = len(re.findall(r"<tr[^>]*>", blk))
        if rows < 4:
            self.bad("参考指南段", f"内容过少（仅 {rows} 行），应含指南表与数值出处表")
        elif rows > 60:
            self.bad("参考指南段",
                     f"{rows} 行，疑似照搬 guidelines.md 全表 —— "
                     "只应列本次实际用到的指南")
        else:
            self.ok("参考指南段", f"{rows} 行，规模合理")

    def check_print_style(self):
        missing = []
        if "print-color-adjust" not in self.raw:
            missing.append("print-color-adjust（打印会丢失风险色块）")
        if "break-inside" not in self.raw:
            missing.append("break-inside（卡片可能被分页截断）")
        if missing:
            self.bad("打印样式", "缺少：" + "；".join(missing))
        else:
            self.ok("打印样式")

    def check_mobile(self):
        # 只在 @media 条件里找断点，避免把 .wrap{max-width:920px} 这类容器宽度误当断点。
        # 断点数值不应写死 640 —— 600 / 680 同样是合法窄屏断点。
        media = " ".join(re.findall(r"@media[^{]*", self.raw))
        bps = sorted({int(x) for x in re.findall(r"max-width:\s*(\d+)px", media)})
        narrow = [b for b in bps if 320 <= b <= 820]
        if narrow:
            self.ok("移动端适配", f"窄屏断点 {narrow} px")
        else:
            self.bad("移动端适配",
                     "缺少窄屏断点（需 @media 内 320~820px 的 max-width）"
                     + (f"，当前仅有 {bps} px" if bps else ""))

    # ── 质量保障（措辞类，只查纯文本）──────────────────────
    def _scan(self, patterns, label, hint):
        """patterns 可为 [(regex, 名称)] 或 [regex]；
        纯 regex 时用实际命中的原文做名称，避免把正则语法打印给人看"""
        hits = []
        for p in patterns:
            rx, name = p if isinstance(p, tuple) else (p, None)
            m = re.search(rx, self.text)
            if m:
                ctx = self.text[max(0, m.start() - 18): m.end() + 18]
                hits.append(f"{name or m.group()}（…{' '.join(ctx.split())}…）")
        if hits:
            self.bad(label, f"{hint}：" + "；".join(hits[:4]))
        else:
            self.ok(label)

    def check_no_absolute_words(self):
        self._scan(ABSOLUTE_WORDS, "无绝对化表述",
                   "医疗结论不得用绝对化词（B5）")

    def check_no_no_treatment(self):
        self._scan(NO_TREATMENT_WORDS, "未说无需治疗",
                   "改为「本次未达干预阈值，建议年度随访并复查 XX」（B3）")

    def check_no_dosage(self):
        self._scan(DOSAGE_PATTERNS, "未给剂量疗程",
                   "用药剂量与疗程须由医生决定（B4）")

    def check_no_dispute(self):
        self._scan(DISPUTE_WORDS, "无医疗纠纷表述",
                   "只能指向标本/采样/文本提取环节并给复查动作（B6）")

    def check_no_ambiguous(self):
        self._scan(AMBIGUOUS_WORDS, "无歧义表述",
                   "须落到具体指标与数值（A3）")

    def check_no_local_path(self):
        self._scan(LOCAL_PATHS, "无本机路径泄漏",
                   "交付物不得暴露本机路径")

    def check_no_internal_terms(self):
        self._scan(INTERNAL_TERMS, "无内部机制名",
                   "只有开发者会用的词不得出现在交付物里")

    def run(self):
        for fn in [
            self.check_no_external, self.check_no_script, self.check_inline_svg,
            self.check_color_scheme, self.check_table_wrap,
            self.check_no_dev_traces, self.check_no_privacy,
            self.check_sections, self.check_toc, self.check_no_emoji,
            self.check_bad_titles, self.check_no_level_codes,
            self.check_sub_numbering, self.check_table_columns,
            self.check_note_budget, self.check_guidelines_section,
            self.check_print_style, self.check_mobile,
            self.check_no_absolute_words, self.check_no_no_treatment,
            self.check_no_dosage, self.check_no_dispute,
            self.check_no_ambiguous, self.check_no_local_path,
            self.check_no_internal_terms,
        ]:
            try:
                fn()
            except Exception as e:
                self.bad(fn.__name__, f"校验器异常：{e}")

        size = os.path.getsize(self.path) / 1024
        print(f"校验对象：{self.path}（{size:.1f} KB）\n")

        if not self.quiet:
            for name, detail in self.passed:
                print(f"  通过  {name}" + (f" —— {detail}" if detail else ""))
            if self.passed and self.failed:
                print()

        for name, detail in self.failed:
            print(f"  失败  {name} —— {detail}")

        print(f"\n合计 {len(self.passed)} 项通过，{len(self.failed)} 项失败")
        return 0 if not self.failed else 1


def main():
    ap = argparse.ArgumentParser(description="报告合规校验")
    ap.add_argument("report", help="HTML 报告路径")
    ap.add_argument("--quiet", action="store_true", help="只输出失败项")
    ap.add_argument("--template", action="store_true",
                    help="模板模式：跳过目录与参考指南段的内容完整性校验")
    args = ap.parse_args()

    if not os.path.exists(args.report):
        print(f"错误：文件不存在 {args.report}", file=sys.stderr)
        sys.exit(2)

    sys.exit(Checker(args.report, args.quiet, args.template).run())


if __name__ == "__main__":
    main()
