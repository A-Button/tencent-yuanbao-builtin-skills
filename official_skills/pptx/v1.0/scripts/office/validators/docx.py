"""
针对 XSD 架构验证 Word 文档 XML 文件的验证器。
"""

import random
import re
import tempfile
import zipfile

import defusedxml.minidom
import lxml.etree

from .base import BaseSchemaValidator


class DOCXSchemaValidator(BaseSchemaValidator):
    """Word (.docx) 文档的架构验证器，继承自基础验证器并添加 Word 特有的校验逻辑。"""

    WORD_2006_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W14_NAMESPACE = "http://schemas.microsoft.com/office/word/2010/wordml"
    W16CID_NAMESPACE = "http://schemas.microsoft.com/office/word/2016/wordml/cid"

    ELEMENT_RELATIONSHIP_TYPES = {}

    def validate(self):
        """
        执行所有 DOCX 文档的验证步骤。

        首先检查 XML 格式是否合法，若不合法则直接返回 False。
        随后依次执行命名空间、唯一 ID、文件引用、内容类型、XSD 架构、
        空白保留、删除标记、插入标记、关系 ID、ID 约束和批注标记的验证。
        最后比较段落数量并返回综合结果。
        """
        if not self.validate_xml():
            return False

        is_valid = True

        for check in [
            self.validate_namespaces,
            self.validate_unique_ids,
            self.validate_file_references,
            self.validate_content_types,
            self.validate_against_xsd,
            self.validate_whitespace_preservation,
            self.validate_deletions,
            self.validate_insertions,
            self.validate_all_relationship_ids,
            self.validate_id_constraints,
            self.validate_comment_markers,
        ]:
            if not check():
                is_valid = False

        self.compare_paragraph_counts()

        return is_valid

    def validate_whitespace_preservation(self):
        """
        验证 document.xml 中所有 w:t 元素的空白保留属性。

        当文本内容以空白字符开头或结尾时，要求元素必须设置 xml:space='preserve'。
        若缺少此属性，则记录为违规错误。
        """
        error_list = []
        xml_space_qualified = f"{{{self.XML_NAMESPACE}}}space"
        ws_leading = re.compile(r"^[ \t\n\r]")
        ws_trailing = re.compile(r"[ \t\n\r]$")

        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue

            try:
                tree = lxml.etree.parse(str(xml_file))
                root_elem = tree.getroot()
                tag_t = f"{{{self.WORD_2006_NAMESPACE}}}t"

                for node in root_elem.iter(tag_t):
                    text_content = node.text
                    if not text_content:
                        continue

                    has_edge_whitespace = (
                        ws_leading.search(text_content) or ws_trailing.search(text_content)
                    )
                    if not has_edge_whitespace:
                        continue

                    space_val = node.attrib.get(xml_space_qualified)
                    if space_val == "preserve":
                        continue

                    raw_repr = repr(text_content)
                    preview = raw_repr[:50] + "..." if len(raw_repr) > 50 else raw_repr
                    rel_path = xml_file.relative_to(self.unpacked_dir)
                    error_list.append(
                        f"  {rel_path}: "
                        f"Line {node.sourceline}: w:t element with whitespace missing xml:space='preserve': {preview}"
                    )

            except (lxml.etree.XMLSyntaxError, Exception) as exc:
                error_list.append(
                    f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {exc}"
                )

        if error_list:
            print(f"FAILED - Found {len(error_list)} whitespace preservation violations:")
            for msg in error_list:
                print(msg)
            return False

        if self.verbose:
            print("PASSED - All whitespace is properly preserved")
        return True

    def validate_deletions(self):
        """
        验证 document.xml 中删除标记的正确性。

        检查 w:del 元素内部是否包含不应出现的 w:t 或 w:instrText 元素。
        w:del 内应使用 w:delText 而非 w:t，使用 w:delInstrText 而非 w:instrText。
        """
        error_list = []
        ns_map = {"w": self.WORD_2006_NAMESPACE}

        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue

            try:
                root_elem = lxml.etree.parse(str(xml_file)).getroot()
                file_rel_path = xml_file.relative_to(self.unpacked_dir)

                for t_node in root_elem.xpath(".//w:del//w:t", namespaces=ns_map):
                    if t_node.text:
                        raw = repr(t_node.text)
                        preview = raw[:50] + "..." if len(raw) > 50 else raw
                        error_list.append(
                            f"  {file_rel_path}: "
                            f"Line {t_node.sourceline}: <w:t> found within <w:del>: {preview}"
                        )

                for instr_node in root_elem.xpath(
                    ".//w:del//w:instrText", namespaces=ns_map
                ):
                    raw = repr(instr_node.text or "")
                    preview = raw[:50] + "..." if len(raw) > 50 else raw
                    error_list.append(
                        f"  {file_rel_path}: "
                        f"Line {instr_node.sourceline}: <w:instrText> found within <w:del> (use <w:delInstrText>): {preview}"
                    )

            except (lxml.etree.XMLSyntaxError, Exception) as exc:
                error_list.append(
                    f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {exc}"
                )

        if error_list:
            print(f"FAILED - Found {len(error_list)} deletion validation violations:")
            for msg in error_list:
                print(msg)
            return False

        if self.verbose:
            print("PASSED - No w:t elements found within w:del elements")
        return True

    def count_paragraphs_in_unpacked(self):
        """
        统计解压后 document.xml 中的段落数量。

        遍历所有 XML 文件，找到 document.xml 并计算其中 w:p 元素的总数。
        """
        para_tag = f".//{{{self.WORD_2006_NAMESPACE}}}p"
        total = 0

        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue

            try:
                root_elem = lxml.etree.parse(str(xml_file)).getroot()
                total = len(root_elem.findall(para_tag))
            except Exception as exc:
                print(f"Error counting paragraphs in unpacked document: {exc}")

        return total

    def count_paragraphs_in_original(self):
        """
        统计原始 DOCX 文件中 document.xml 的段落数量。

        将原始文件解压到临时目录，然后解析 word/document.xml 计算 w:p 元素数量。
        若没有提供原始文件则返回 0。
        """
        if self.original_file is None:
            return 0

        para_tag = f".//{{{self.WORD_2006_NAMESPACE}}}p"
        result = 0

        try:
            with tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(self.original_file, "r") as zf:
                    zf.extractall(tmp)

                doc_path = tmp + "/word/document.xml"
                root_elem = lxml.etree.parse(doc_path).getroot()
                result = len(root_elem.findall(para_tag))

        except Exception as exc:
            print(f"Error counting paragraphs in original document: {exc}")

        return result

    def validate_insertions(self):
        """
        验证 document.xml 中插入标记的正确性。

        检查 w:ins 元素内部（排除 w:del 嵌套情况）是否包含 w:delText 元素。
        插入区域中不应出现删除文本标记。
        """
        error_list = []
        ns_map = {"w": self.WORD_2006_NAMESPACE}

        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue

            try:
                root_elem = lxml.etree.parse(str(xml_file)).getroot()
                file_rel_path = xml_file.relative_to(self.unpacked_dir)

                bad_nodes = root_elem.xpath(
                    ".//w:ins//w:delText[not(ancestor::w:del)]", namespaces=ns_map
                )

                for node in bad_nodes:
                    raw = repr(node.text or "")
                    preview = raw[:50] + "..." if len(raw) > 50 else raw
                    error_list.append(
                        f"  {file_rel_path}: "
                        f"Line {node.sourceline}: <w:delText> within <w:ins>: {preview}"
                    )

            except (lxml.etree.XMLSyntaxError, Exception) as exc:
                error_list.append(
                    f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {exc}"
                )

        if error_list:
            print(f"FAILED - Found {len(error_list)} insertion validation violations:")
            for msg in error_list:
                print(msg)
            return False

        if self.verbose:
            print("PASSED - No w:delText elements within w:ins elements")
        return True

    def compare_paragraph_counts(self):
        """
        对比原始文档和修改后文档的段落数，并输出差异。
        """
        orig = self.count_paragraphs_in_original()
        current = self.count_paragraphs_in_unpacked()

        delta = current - orig
        delta_display = f"+{delta}" if delta > 0 else str(delta)
        print(f"\nParagraphs: {orig} → {current} ({delta_display})")

    def _decode_id_value(self, val: str, base: int = 16) -> int:
        """
        将字符串形式的 ID 值按指定进制解析为整数。

        参数:
            val: 待解析的字符串值
            base: 进制，默认为 16（十六进制）
        """
        return int(val, base)

    def validate_id_constraints(self):
        """
        验证文档中 paraId 和 durableId 属性的数值约束。

        paraId 必须小于 0x80000000。
        durableId 必须小于 0x7FFFFFFF，在 numbering.xml 中以十进制表示，
        在其他文件中以十六进制表示。
        """
        error_list = []
        attr_para_id = f"{{{self.W14_NAMESPACE}}}paraId"
        attr_durable_id = f"{{{self.W16CID_NAMESPACE}}}durableId"

        for xml_file in self.xml_files:
            try:
                tree = lxml.etree.parse(str(xml_file))
                for node in tree.iter():
                    pid = node.get(attr_para_id)
                    if pid is not None:
                        if self._decode_id_value(pid, base=16) >= 0x80000000:
                            error_list.append(
                                f"  {xml_file.name}:{node.sourceline}: paraId={pid} >= 0x80000000"
                            )

                    did = node.get(attr_durable_id)
                    if did is not None:
                        if xml_file.name == "numbering.xml":
                            try:
                                if self._decode_id_value(did, base=10) >= 0x7FFFFFFF:
                                    error_list.append(
                                        f"  {xml_file.name}:{node.sourceline}: "
                                        f"durableId={did} >= 0x7FFFFFFF"
                                    )
                            except ValueError:
                                error_list.append(
                                    f"  {xml_file.name}:{node.sourceline}: "
                                    f"durableId={did} must be decimal in numbering.xml"
                                )
                        else:
                            if self._decode_id_value(did, base=16) >= 0x7FFFFFFF:
                                error_list.append(
                                    f"  {xml_file.name}:{node.sourceline}: "
                                    f"durableId={did} >= 0x7FFFFFFF"
                                )
            except Exception:
                pass

        if error_list:
            print(f"FAILED - {len(error_list)} ID constraint violations:")
            for entry in error_list:
                print(entry)
        elif self.verbose:
            print("PASSED - All paraId/durableId values within constraints")
        return not error_list

    def validate_comment_markers(self):
        """
        验证文档中批注标记的完整性和一致性。

        检查以下内容：
        1. 每个 commentRangeEnd 都有对应的 commentRangeStart
        2. 每个 commentRangeStart 都有对应的 commentRangeEnd
        3. 文档中引用的批注 ID 在 comments.xml 中确实存在
        """
        error_list = []

        document_xml = None
        comments_xml = None
        for xml_file in self.xml_files:
            if xml_file.name == "document.xml" and "word" in str(xml_file):
                document_xml = xml_file
            elif xml_file.name == "comments.xml":
                comments_xml = xml_file

        if document_xml is None:
            if self.verbose:
                print("PASSED - No document.xml found (skipping comment validation)")
            return True

        try:
            doc_tree = lxml.etree.parse(str(document_xml))
            doc_root = doc_tree.getroot()
            ns_map = {"w": self.WORD_2006_NAMESPACE}
            w_id = f"{{{self.WORD_2006_NAMESPACE}}}id"

            starts = {
                el.get(w_id)
                for el in doc_root.xpath(".//w:commentRangeStart", namespaces=ns_map)
            }
            ends = {
                el.get(w_id)
                for el in doc_root.xpath(".//w:commentRangeEnd", namespaces=ns_map)
            }
            refs = {
                el.get(w_id)
                for el in doc_root.xpath(".//w:commentReference", namespaces=ns_map)
            }

            sort_key = lambda x: int(x) if x and x.isdigit() else 0

            for cid in sorted(ends - starts, key=sort_key):
                error_list.append(
                    f'  document.xml: commentRangeEnd id="{cid}" has no matching commentRangeStart'
                )

            for cid in sorted(starts - ends, key=sort_key):
                error_list.append(
                    f'  document.xml: commentRangeStart id="{cid}" has no matching commentRangeEnd'
                )

            if comments_xml and comments_xml.exists():
                comments_tree = lxml.etree.parse(str(comments_xml))
                comments_root = comments_tree.getroot()
                defined_ids = {
                    el.get(w_id)
                    for el in comments_root.xpath(".//w:comment", namespaces=ns_map)
                }

                all_marker_ids = starts | ends | refs
                dangling = all_marker_ids - defined_ids
                for cid in sorted(dangling, key=sort_key):
                    if cid:
                        error_list.append(
                            f'  document.xml: marker id="{cid}" references non-existent comment'
                        )

        except (lxml.etree.XMLSyntaxError, Exception) as exc:
            error_list.append(f"  Error parsing XML: {exc}")

        if error_list:
            print(f"FAILED - {len(error_list)} comment marker violations:")
            for msg in error_list:
                print(msg)
            return False

        if self.verbose:
            print("PASSED - All comment markers properly paired")
        return True

    def repair(self) -> int:
        """
        执行所有修复操作，包括基类修复和 durableId 修复。

        返回修复的总数量。
        """
        total_repairs = super().repair()
        total_repairs += self.repair_durableId()
        return total_repairs

    def repair_durableId(self) -> int:
        """
        修复超出范围的 durableId 属性值。

        对于 numbering.xml 中的 durableId，使用十进制格式；
        对于其他文件中的 durableId，使用八位十六进制大写格式。
        超过 0x7FFFFFFE 的值将被替换为 [1, 0x7FFFFFFE] 范围内的随机值。
        """
        repair_count = 0

        for xml_file in self.xml_files:
            try:
                raw_content = xml_file.read_text(encoding="utf-8")
                dom = defusedxml.minidom.parseString(raw_content)
                file_modified = False

                for elem in dom.getElementsByTagName("*"):
                    if not elem.hasAttribute("w16cid:durableId"):
                        continue

                    current_id = elem.getAttribute("w16cid:durableId")
                    should_repair = False

                    if xml_file.name == "numbering.xml":
                        try:
                            should_repair = (
                                self._decode_id_value(current_id, base=10) >= 0x7FFFFFFF
                            )
                        except ValueError:
                            should_repair = True
                    else:
                        try:
                            should_repair = (
                                self._decode_id_value(current_id, base=16) >= 0x7FFFFFFF
                            )
                        except ValueError:
                            should_repair = True

                    if not should_repair:
                        continue

                    rand_val = random.randint(1, 0x7FFFFFFE)
                    replacement = (
                        str(rand_val) if xml_file.name == "numbering.xml"
                        else f"{rand_val:08X}"
                    )

                    elem.setAttribute("w16cid:durableId", replacement)
                    print(
                        f"  Repaired: {xml_file.name}: durableId {current_id} → {replacement}"
                    )
                    repair_count += 1
                    file_modified = True

                if file_modified:
                    xml_file.write_bytes(dom.toxml(encoding="UTF-8"))

            except Exception:
                pass

        return repair_count


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
