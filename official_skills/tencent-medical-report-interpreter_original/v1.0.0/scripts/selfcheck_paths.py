#!/usr/bin/env python3
"""
包完整性自检（selfcheck_paths.py）

用途：修改技能包后、打包分发前必跑。三项检查必须全过：
      A 零写死本机路径
      B SKILL_DIR 探测目标指向真实存在的目录
      C 文档引用的包内文件真实存在

为什么需要这三项：
  A —— 写死 `/Users/<某个真实用户名>/...` 或带版本号的解释器路径
       （`.../versions/<具体版本>/bin/python3`），换机器、换用户、解释器升版
       就全部失效，分发出去即是废包，而且失效时的报错方向极具误导性。
  B —— 光满足 A 还不够。2026-09-20 实测踩过：目录改名后，SKILL.md 里的
       `SKILL_DIR=$(ls -d "$HOME/.workbuddy/skills/<旧目录名>" ...)` 仍是合法的
       变量写法、A 项照样通过，但探测目标已不存在，`$SKILL_DIR` 为空，
       三个脚本一条都跑不起来。**A 查不出这类问题，必须单列 B。**
  C —— 同源问题：改名或删文件后，SKILL.md 里的 `@references/x.md` 会静默失效。
       模型读不到就只能凭记忆编，属医疗场景不可接受的失败模式。

设计要点（为什么 A 不用一行 grep）：
  裸 grep 会命中文档里「禁止这样写」的规则说明本身与校验器的模式定义，
  永远非零输出，自检就失去意义。A 项的所有模式都**要求出现具体取值**
  （真实用户名 / 真实版本号），因此 `<用户名>`、`<版本号>` 这类占位写法
  与本文件自身的模式定义都不会被误判，无需任何豁免清单。

注意：
  B 项以「被扫描目录的名字」为基准比对。若在改名副本或临时目录上运行会误报，
  请在真实安装目录（`~/.workbuddy/skills/<技能目录>`）上跑。

用法：
  python3 selfcheck_paths.py             # 扫描脚本所在技能包
  python3 selfcheck_paths.py <目录>

退出码：
  0 = 三项全过    1 = 存在问题
"""

import os
import re
import sys

SCAN_EXT = (".md", ".py", ".html", ".htm", ".json", ".sh", ".txt")
DOC_FILES = ("SKILL.md", "README.md")

# ── A 项模式：每条都要求「具体取值」，占位符写法不会命中 ──────────────
PATTERNS = [
    (re.compile(r"/Users/[A-Za-z0-9._-]+"), "macOS 用户主目录绝对路径"),
    (re.compile(r"/home/[A-Za-z0-9._-]+"), "Linux 用户主目录绝对路径"),
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9._-]+"), "Windows 用户主目录绝对路径"),
    (re.compile(r"versions/\d+\.\d[\d.]*/bin"), "带版本号的解释器路径"),
    (re.compile(r"/tmp/[A-Za-z0-9_-]"), "本机临时目录"),
    (re.compile(r"/var/folders/[A-Za-z0-9]"), "本机临时目录"),
]

# ── B 项：SKILL_DIR 探测目标 ────────────────────────────────────
# 匹配 $HOME/.workbuddy/skills/<名> 与 ./.workbuddy/skills/<名> 两种安装位置写法
SKILLDIR_RE = re.compile(
    r'(?:\$HOME|~|\.)/\.workbuddy/skills/([A-Za-z0-9._-]+)'
)

# ── C 项：文档里对包内文件的引用 ─────────────────────────────────
# 形如 @references/x.md、@scripts/x.py、`templates/x.md`、scripts/x.py
REF_RE = re.compile(
    r'@?\b(references|scripts|templates|examples)/([A-Za-z0-9._-]+\.(?:md|py|html|json))'
)


def check_paths(root):
    """A：写死本机路径"""
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
        for fn in filenames:
            if not fn.endswith(SCAN_EXT):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                for rx, label in PATTERNS:
                    m = rx.search(line)
                    if m:
                        hits.append((os.path.relpath(path, root), i, label, m.group()))
    return hits


def check_skilldir(root):
    """B：SKILL_DIR 探测目标必须等于本包实际目录名"""
    actual = os.path.basename(os.path.abspath(root))
    hits = []
    for fn in DOC_FILES:
        path = os.path.join(root, fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                for name in SKILLDIR_RE.findall(line):
                    if name != actual:
                        hits.append((
                            fn, i,
                            f"探测目标 `{name}` 与实际目录名 `{actual}` 不一致",
                            "改名后漏改会导致 $SKILL_DIR 为空，所有脚本失效",
                        ))
    return hits, actual


def check_refs(root):
    """C：文档引用的包内文件必须存在"""
    hits = []
    seen = set()
    for fn in DOC_FILES:
        path = os.path.join(root, fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                for sub, name in REF_RE.findall(line):
                    rel = f"{sub}/{name}"
                    if (fn, rel) in seen:
                        continue
                    seen.add((fn, rel))
                    if not os.path.exists(os.path.join(root, rel)):
                        hits.append((fn, i, f"引用的包内文件不存在：{rel}", ""))
    return hits


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    if not os.path.isdir(root):
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        sys.exit(2)

    print(f"扫描目录：{root}\n")
    failed = 0

    a = check_paths(root)
    if a:
        failed += len(a)
        for rel, ln, label, frag in a:
            print(f"  失败  [A 本机路径] {rel}:{ln}  {label} —— {frag}")
    else:
        print("  通过  [A] 零写死路径，可跨机器分发")

    b, actual = check_skilldir(root)
    if b:
        failed += len(b)
        for rel, ln, label, why in b:
            print(f"  失败  [B 探测目标] {rel}:{ln}  {label}")
            print(f"                    原因：{why}")
    else:
        print(f"  通过  [B] SKILL_DIR 探测目标与实际目录名一致（{actual}）")

    c = check_refs(root)
    if c:
        failed += len(c)
        for rel, ln, label, _ in c:
            print(f"  失败  [C 包内引用] {rel}:{ln}  {label}")
    else:
        print("  通过  [C] 文档引用的包内文件全部存在")

    if failed:
        print(f"\n合计 {failed} 项失败；A 改为 SKILL_DIR + PY 变量写法，"
              f"B 同步目录名，C 补文件或改引用")
        return 1
    print("\n合计 0 项失败，三项全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
