"""
Word 文档修订（tracked changes）校验器。
"""

import subprocess
import tempfile
import zipfile
from pathlib import Path


class RedliningValidator:
    """校验 Word 文档中的修订标记是否符合预期。"""

    def __init__(self, unpacked_dir, original_docx, verbose=False, author="yuanbao"):
        """
        初始化校验器。

        参数:
            unpacked_dir: 已解压的 docx 目录路径
            original_docx: 原始 docx 文件路径
            verbose: 是否输出详细日志
            author: 需要校验的修订作者名称
        """
        self.unpacked_dir = Path(unpacked_dir)
        self.original_docx = Path(original_docx)
        self.verbose = verbose
        self.author = author
        self.namespaces = {
            "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        }

    def repair(self) -> int:
        """修复操作（当前未实现，始终返回 0）。"""
        return 0

    def validate(self):
        """
        校验文档修订标记的正确性。

        将修改后的文档与原始文档进行比对：移除指定作者的修订标记后，
        两者的纯文本内容应完全一致。不一致则说明存在未正确标记的改动。

        返回:
            bool: 校验通过返回 True，否则返回 False
        """
        modified_xml = self.unpacked_dir / "word" / "document.xml"
        if not modified_xml.exists():
            print(f"FAILED - Modified document.xml not found at {modified_xml}")
            return False

        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(modified_xml)
            root = tree.getroot()

            ns_w = self.namespaces["w"]
            all_del = root.findall(".//w:del", self.namespaces)
            all_ins = root.findall(".//w:ins", self.namespaces)

            author_key = f"{{{ns_w}}}author"
            matched_del = [e for e in all_del if e.get(author_key) == self.author]
            matched_ins = [e for e in all_ins if e.get(author_key) == self.author]

            if len(matched_del) == 0 and len(matched_ins) == 0:
                if self.verbose:
                    print(f"PASSED - No tracked changes by {self.author} found.")
                return True

        except Exception:
            pass

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            try:
                with zipfile.ZipFile(self.original_docx, "r") as zf:
                    zf.extractall(tmp_path)
            except Exception as exc:
                print(f"FAILED - Error unpacking original docx: {exc}")
                return False

            original_xml = tmp_path / "word" / "document.xml"
            if not original_xml.exists():
                print(
                    f"FAILED - Original document.xml not found in {self.original_docx}"
                )
                return False

            try:
                import xml.etree.ElementTree as ET

                mod_tree = ET.parse(modified_xml)
                mod_root = mod_tree.getroot()
                orig_tree = ET.parse(original_xml)
                orig_root = orig_tree.getroot()
            except ET.ParseError as exc:
                print(f"FAILED - Error parsing XML files: {exc}")
                return False

            self._strip_author_revisions(orig_root)
            self._strip_author_revisions(mod_root)

            text_modified = self._collect_paragraph_text(mod_root)
            text_original = self._collect_paragraph_text(orig_root)

            if text_modified != text_original:
                msg = self._build_diff_report(text_original, text_modified)
                print(msg)
                return False

            if self.verbose:
                print(f"PASSED - All changes by {self.author} are properly tracked")
            return True

    def _build_diff_report(self, original_text, modified_text):
        """
        生成详细的差异报告。

        参数:
            original_text: 原始文档提取的纯文本
            modified_text: 修改后文档提取的纯文本

        返回:
            str: 包含错误原因和具体差异的报告字符串
        """
        sections = [
            f"FAILED - Document text doesn't match after removing {self.author}'s tracked changes",
            "",
            "Likely causes:",
            "  1. Modified text inside another author's <w:ins> or <w:del> tags",
            "  2. Made edits without proper tracked changes",
            "  3. Didn't nest <w:del> inside <w:ins> when deleting another's insertion",
            "",
            "For pre-redlined documents, use correct patterns:",
            "  - To reject another's INSERTION: Nest <w:del> inside their <w:ins>",
            "  - To restore another's DELETION: Add new <w:ins> AFTER their <w:del>",
            "",
        ]

        word_diff = self._compute_word_diff(original_text, modified_text)
        if word_diff is not None:
            sections.extend(["Differences:", "============", word_diff])
        else:
            sections.append("Unable to generate word diff (git not available)")

        return "\n".join(sections)

    def _compute_word_diff(self, original_text, modified_text):
        """
        利用 git diff 生成逐字差异。

        先尝试按字符级别对比（--word-diff-regex=.），若无结果则退回到
        默认的 word-diff 模式。

        参数:
            original_text: 原始纯文本
            modified_text: 修改后的纯文本

        返回:
            str | None: 差异内容字符串，或在 git 不可用时返回 None
        """
        try:
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)

                file_orig = td_path / "original.txt"
                file_mod = td_path / "modified.txt"

                file_orig.write_text(original_text, encoding="utf-8")
                file_mod.write_text(modified_text, encoding="utf-8")

                proc = subprocess.run(
                    [
                        "git",
                        "diff",
                        "--word-diff=plain",
                        "--word-diff-regex=.",
                        "-U0",
                        "--no-index",
                        str(file_orig),
                        str(file_mod),
                    ],
                    capture_output=True,
                    text=True,
                )

                extracted = self._parse_diff_output(proc.stdout)
                if extracted is not None:
                    return extracted

                proc = subprocess.run(
                    [
                        "git",
                        "diff",
                        "--word-diff=plain",
                        "-U0",
                        "--no-index",
                        str(file_orig),
                        str(file_mod),
                    ],
                    capture_output=True,
                    text=True,
                )

                return self._parse_diff_output(proc.stdout)

        except (subprocess.CalledProcessError, FileNotFoundError, Exception):
            pass

        return None

    @staticmethod
    def _parse_diff_output(raw_output):
        """
        从 git diff 输出中提取有效内容行（跳过头部元数据）。

        参数:
            raw_output: git diff 命令的标准输出

        返回:
            str | None: 拼接后的差异内容，无有效内容时返回 None
        """
        if not raw_output.strip():
            return None

        lines = raw_output.split("\n")
        content = []
        started = False
        for line in lines:
            if line.startswith("@@"):
                started = True
                continue
            if started and line.strip():
                content.append(line)

        if content:
            return "\n".join(content)
        return None

    def _strip_author_revisions(self, root):
        """
        从 XML 树中移除指定作者的所有修订标记。

        对于 <w:ins> 标记：直接删除整个节点（即撤销插入）。
        对于 <w:del> 标记：将其中的 <w:delText> 还原为 <w:t>，
        并把子节点提升到父级（即撤销删除）。

        参数:
            root: XML 文档的根元素
        """
        ns_w = self.namespaces["w"]
        tag_ins = f"{{{ns_w}}}ins"
        tag_del = f"{{{ns_w}}}del"
        attr_author = f"{{{ns_w}}}author"

        for parent in root.iter():
            removable = [
                ch for ch in parent
                if ch.tag == tag_ins and ch.get(attr_author) == self.author
            ]
            for node in removable:
                parent.remove(node)

        tag_deltext = f"{{{ns_w}}}delText"
        tag_t = f"{{{ns_w}}}t"

        for parent in root.iter():
            candidates = []
            for child in parent:
                if child.tag == tag_del and child.get(attr_author) == self.author:
                    idx = list(parent).index(child)
                    candidates.append((child, idx))

            for del_node, position in reversed(candidates):
                for descendant in del_node.iter():
                    if descendant.tag == tag_deltext:
                        descendant.tag = tag_t

                children = list(del_node)
                for ch in reversed(children):
                    parent.insert(position, ch)
                parent.remove(del_node)

    def _collect_paragraph_text(self, root):
        """
        从 XML 树中提取所有段落的纯文本内容。

        遍历所有 <w:p> 元素，收集其中 <w:t> 节点的文本，
        按段落拼接后以换行符连接。

        参数:
            root: XML 文档的根元素

        返回:
            str: 拼接后的文档纯文本
        """
        ns_w = self.namespaces["w"]
        tag_p = f"{{{ns_w}}}p"
        tag_t = f"{{{ns_w}}}t"

        result = []
        for p_node in root.findall(f".//{tag_p}"):
            fragments = []
            for t_node in p_node.findall(f".//{tag_t}"):
                if t_node.text:
                    fragments.append(t_node.text)
            joined = "".join(fragments)
            if joined:
                result.append(joined)

        return "\n".join(result)


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
