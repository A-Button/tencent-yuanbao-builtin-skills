"""Word 文档修订标记验证器。"""

import subprocess
import tempfile
import zipfile
from pathlib import Path


class RedliningValidator:

    def __init__(self, unpacked_dir, original_docx, verbose=False, author="Assistant"):
        self.unpacked_dir = Path(unpacked_dir)
        self.original_docx = Path(original_docx)
        self.verbose = verbose
        self.author = author
        self.namespaces = {
            "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        }

    def repair(self) -> int:
        return 0

    def validate(self):
        modified_file = self.unpacked_dir / "word" / "document.xml"
        if not modified_file.exists():
            print(f"FAILED - Modified document.xml not found at {modified_file}")
            return False

        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(modified_file)
            root = tree.getroot()
            w_author = f"{{{self.namespaces['w']}}}author"

            del_elems = root.findall(".//w:del", self.namespaces)
            ins_elems = root.findall(".//w:ins", self.namespaces)

            author_dels = [e for e in del_elems if e.get(w_author) == self.author]
            author_inss = [e for e in ins_elems if e.get(w_author) == self.author]

            if not author_dels and not author_inss:
                if self.verbose:
                    print(f"PASSED - No tracked changes by {self.author} found.")
                return True

        except Exception:
            pass

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            try:
                with zipfile.ZipFile(self.original_docx, "r") as zf:
                    zf.extractall(tmp)
            except Exception as e:
                print(f"FAILED - Error unpacking original docx: {e}")
                return False

            original_file = tmp / "word" / "document.xml"
            if not original_file.exists():
                print(f"FAILED - Original document.xml not found in {self.original_docx}")
                return False

            try:
                import xml.etree.ElementTree as ET

                modified_root = ET.parse(modified_file).getroot()
                original_root = ET.parse(original_file).getroot()
            except ET.ParseError as e:
                print(f"FAILED - Error parsing XML files: {e}")
                return False

            self._remove_author_tracked_changes(original_root)
            self._remove_author_tracked_changes(modified_root)

            modified_text = self._extract_text_content(modified_root)
            original_text = self._extract_text_content(original_root)

            if modified_text != original_text:
                print(self._generate_detailed_diff(original_text, modified_text))
                return False

            if self.verbose:
                print(f"PASSED - All changes by {self.author} are properly tracked")
            return True

    def _generate_detailed_diff(self, original_text, modified_text):
        parts = [
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

        diff = self._get_git_word_diff(original_text, modified_text)
        if diff:
            parts.extend(["Differences:", "============", diff])
        else:
            parts.append("Unable to generate word diff (git not available)")

        return "\n".join(parts)

    def _get_git_word_diff(self, original_text, modified_text):
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                orig_f = tmp / "original.txt"
                mod_f = tmp / "modified.txt"

                orig_f.write_text(original_text, encoding="utf-8")
                mod_f.write_text(modified_text, encoding="utf-8")

                for extra_args in [["--word-diff-regex=."], []]:
                    result = subprocess.run(
                        [
                            "git", "diff", "--word-diff=plain",
                            *extra_args, "-U0", "--no-index",
                            str(orig_f), str(mod_f),
                        ],
                        capture_output=True, text=True,
                    )

                    if result.stdout.strip():
                        content_lines = []
                        in_content = False
                        for line in result.stdout.split("\n"):
                            if line.startswith("@@"):
                                in_content = True
                                continue
                            if in_content and line.strip():
                                content_lines.append(line)
                        if content_lines:
                            return "\n".join(content_lines)

        except (subprocess.CalledProcessError, FileNotFoundError, Exception):
            pass

        return None

    def _remove_author_tracked_changes(self, root):
        ins_tag = f"{{{self.namespaces['w']}}}ins"
        del_tag = f"{{{self.namespaces['w']}}}del"
        author_attr = f"{{{self.namespaces['w']}}}author"

        for parent in root.iter():
            to_remove = [
                child for child in parent
                if child.tag == ins_tag and child.get(author_attr) == self.author
            ]
            for elem in to_remove:
                parent.remove(elem)

        deltext_tag = f"{{{self.namespaces['w']}}}delText"
        t_tag = f"{{{self.namespaces['w']}}}t"

        for parent in root.iter():
            to_process = [
                (child, list(parent).index(child))
                for child in parent
                if child.tag == del_tag and child.get(author_attr) == self.author
            ]

            for del_elem, idx in reversed(to_process):
                for elem in del_elem.iter():
                    if elem.tag == deltext_tag:
                        elem.tag = t_tag

                for child in reversed(list(del_elem)):
                    parent.insert(idx, child)
                parent.remove(del_elem)

    def _extract_text_content(self, root):
        p_tag = f"{{{self.namespaces['w']}}}p"
        t_tag = f"{{{self.namespaces['w']}}}t"

        paragraphs = []
        for p in root.findall(f".//{p_tag}"):
            text = "".join(
                t.text for t in p.findall(f".//{t_tag}") if t.text
            )
            if text:
                paragraphs.append(text)

        return "\n".join(paragraphs)


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
