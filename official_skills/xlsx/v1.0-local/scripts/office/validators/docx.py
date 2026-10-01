"""Word 文档 XML 文件的 XSD schema 验证器。"""

import random
import re
import tempfile
import zipfile

import defusedxml.minidom
import lxml.etree

from .base import BaseSchemaValidator


class DOCXSchemaValidator(BaseSchemaValidator):

    WORD_2006_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W14_NAMESPACE = "http://schemas.microsoft.com/office/word/2010/wordml"
    W16CID_NAMESPACE = "http://schemas.microsoft.com/office/word/2016/wordml/cid"

    ELEMENT_RELATIONSHIP_TYPES = {}

    def validate(self):
        if not self.validate_xml():
            return False

        checks = [
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
        ]

        all_valid = all(check() for check in checks)
        self.compare_paragraph_counts()
        return all_valid

    def validate_whitespace_preservation(self):
        errors = []

        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue

            try:
                root = lxml.etree.parse(str(xml_file)).getroot()

                for elem in root.iter(f"{{{self.WORD_2006_NAMESPACE}}}t"):
                    if not elem.text:
                        continue
                    text = elem.text
                    if re.search(r"^[ \t\n\r]", text) or re.search(r"[ \t\n\r]$", text):
                        xml_space = f"{{{self.XML_NAMESPACE}}}space"
                        if xml_space not in elem.attrib or elem.attrib[xml_space] != "preserve":
                            preview = repr(text)[:50] + "..." if len(repr(text)) > 50 else repr(text)
                            errors.append(
                                f"  {xml_file.relative_to(self.unpacked_dir)}: "
                                f"Line {elem.sourceline}: w:t element with whitespace missing xml:space='preserve': {preview}"
                            )

            except (lxml.etree.XMLSyntaxError, Exception) as e:
                errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {e}")

        if errors:
            print(f"FAILED - Found {len(errors)} whitespace preservation violations:")
            for err in errors:
                print(err)
            return False

        if self.verbose:
            print("PASSED - All whitespace is properly preserved")
        return True

    def validate_deletions(self):
        errors = []

        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue

            try:
                root = lxml.etree.parse(str(xml_file)).getroot()
                ns = {"w": self.WORD_2006_NAMESPACE}

                for t_elem in root.xpath(".//w:del//w:t", namespaces=ns):
                    if t_elem.text:
                        preview = repr(t_elem.text)[:50] + "..." if len(repr(t_elem.text)) > 50 else repr(t_elem.text)
                        errors.append(
                            f"  {xml_file.relative_to(self.unpacked_dir)}: "
                            f"Line {t_elem.sourceline}: <w:t> found within <w:del>: {preview}"
                        )

                for instr in root.xpath(".//w:del//w:instrText", namespaces=ns):
                    preview = repr(instr.text or "")[:50] + "..." if len(repr(instr.text or "")) > 50 else repr(instr.text or "")
                    errors.append(
                        f"  {xml_file.relative_to(self.unpacked_dir)}: "
                        f"Line {instr.sourceline}: <w:instrText> found within <w:del> (use <w:delInstrText>): {preview}"
                    )

            except (lxml.etree.XMLSyntaxError, Exception) as e:
                errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {e}")

        if errors:
            print(f"FAILED - Found {len(errors)} deletion validation violations:")
            for err in errors:
                print(err)
            return False

        if self.verbose:
            print("PASSED - No w:t elements found within w:del elements")
        return True

    def count_paragraphs_in_unpacked(self):
        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue
            try:
                root = lxml.etree.parse(str(xml_file)).getroot()
                return len(root.findall(f".//{{{self.WORD_2006_NAMESPACE}}}p"))
            except Exception as e:
                print(f"Error counting paragraphs in unpacked document: {e}")
        return 0

    def count_paragraphs_in_original(self):
        if self.original_file is None:
            return 0

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(self.original_file, "r") as zf:
                    zf.extractall(tmpdir)
                root = lxml.etree.parse(f"{tmpdir}/word/document.xml").getroot()
                return len(root.findall(f".//{{{self.WORD_2006_NAMESPACE}}}p"))
        except Exception as e:
            print(f"Error counting paragraphs in original document: {e}")
            return 0

    def validate_insertions(self):
        errors = []

        for xml_file in self.xml_files:
            if xml_file.name != "document.xml":
                continue

            try:
                root = lxml.etree.parse(str(xml_file)).getroot()
                ns = {"w": self.WORD_2006_NAMESPACE}

                for elem in root.xpath(".//w:ins//w:delText[not(ancestor::w:del)]", namespaces=ns):
                    preview = repr(elem.text or "")[:50] + "..." if len(repr(elem.text or "")) > 50 else repr(elem.text or "")
                    errors.append(
                        f"  {xml_file.relative_to(self.unpacked_dir)}: "
                        f"Line {elem.sourceline}: <w:delText> within <w:ins>: {preview}"
                    )

            except (lxml.etree.XMLSyntaxError, Exception) as e:
                errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {e}")

        if errors:
            print(f"FAILED - Found {len(errors)} insertion validation violations:")
            for err in errors:
                print(err)
            return False

        if self.verbose:
            print("PASSED - No w:delText elements within w:ins elements")
        return True

    def compare_paragraph_counts(self):
        orig = self.count_paragraphs_in_original()
        curr = self.count_paragraphs_in_unpacked()
        diff = curr - orig
        sign = f"+{diff}" if diff > 0 else str(diff)
        print(f"\nParagraphs: {orig} → {curr} ({sign})")

    def _parse_id_value(self, val: str, base: int = 16) -> int:
        return int(val, base)

    def validate_id_constraints(self):
        errors = []
        para_id_attr = f"{{{self.W14_NAMESPACE}}}paraId"
        durable_id_attr = f"{{{self.W16CID_NAMESPACE}}}durableId"

        for xml_file in self.xml_files:
            try:
                for elem in lxml.etree.parse(str(xml_file)).iter():
                    if val := elem.get(para_id_attr):
                        if self._parse_id_value(val, base=16) >= 0x80000000:
                            errors.append(
                                f"  {xml_file.name}:{elem.sourceline}: paraId={val} >= 0x80000000"
                            )

                    if val := elem.get(durable_id_attr):
                        if xml_file.name == "numbering.xml":
                            try:
                                if self._parse_id_value(val, base=10) >= 0x7FFFFFFF:
                                    errors.append(
                                        f"  {xml_file.name}:{elem.sourceline}: "
                                        f"durableId={val} >= 0x7FFFFFFF"
                                    )
                            except ValueError:
                                errors.append(
                                    f"  {xml_file.name}:{elem.sourceline}: "
                                    f"durableId={val} must be decimal in numbering.xml"
                                )
                        else:
                            if self._parse_id_value(val, base=16) >= 0x7FFFFFFF:
                                errors.append(
                                    f"  {xml_file.name}:{elem.sourceline}: "
                                    f"durableId={val} >= 0x7FFFFFFF"
                                )
            except Exception:
                pass

        if errors:
            print(f"FAILED - {len(errors)} ID constraint violations:")
            for err in errors:
                print(err)
        elif self.verbose:
            print("PASSED - All paraId/durableId values within constraints")
        return not errors

    def validate_comment_markers(self):
        errors = []

        document_xml = None
        comments_xml = None
        for xml_file in self.xml_files:
            if xml_file.name == "document.xml" and "word" in str(xml_file):
                document_xml = xml_file
            elif xml_file.name == "comments.xml":
                comments_xml = xml_file

        if not document_xml:
            if self.verbose:
                print("PASSED - No document.xml found (skipping comment validation)")
            return True

        try:
            doc_root = lxml.etree.parse(str(document_xml)).getroot()
            ns = {"w": self.WORD_2006_NAMESPACE}
            w_id = f"{{{self.WORD_2006_NAMESPACE}}}id"

            range_starts = {
                e.get(w_id) for e in doc_root.xpath(".//w:commentRangeStart", namespaces=ns)
            }
            range_ends = {
                e.get(w_id) for e in doc_root.xpath(".//w:commentRangeEnd", namespaces=ns)
            }
            references = {
                e.get(w_id) for e in doc_root.xpath(".//w:commentReference", namespaces=ns)
            }

            for cid in sorted(range_ends - range_starts, key=lambda x: int(x) if x and x.isdigit() else 0):
                errors.append(f'  document.xml: commentRangeEnd id="{cid}" has no matching commentRangeStart')

            for cid in sorted(range_starts - range_ends, key=lambda x: int(x) if x and x.isdigit() else 0):
                errors.append(f'  document.xml: commentRangeStart id="{cid}" has no matching commentRangeEnd')

            if comments_xml and comments_xml.exists():
                comments_root = lxml.etree.parse(str(comments_xml)).getroot()
                comment_ids = {
                    e.get(w_id) for e in comments_root.xpath(".//w:comment", namespaces=ns)
                }

                marker_ids = range_starts | range_ends | references
                for cid in sorted(
                    marker_ids - comment_ids,
                    key=lambda x: int(x) if x and x.isdigit() else 0,
                ):
                    if cid:
                        errors.append(f'  document.xml: marker id="{cid}" references non-existent comment')

        except (lxml.etree.XMLSyntaxError, Exception) as e:
            errors.append(f"  Error parsing XML: {e}")

        if errors:
            print(f"FAILED - {len(errors)} comment marker violations:")
            for err in errors:
                print(err)
            return False

        if self.verbose:
            print("PASSED - All comment markers properly paired")
        return True

    def repair(self) -> int:
        repairs = super().repair()
        repairs += self.repair_durableId()
        return repairs

    def repair_durableId(self) -> int:
        repairs = 0

        for xml_file in self.xml_files:
            try:
                content = xml_file.read_text(encoding="utf-8")
                dom = defusedxml.minidom.parseString(content)
                modified = False

                for elem in dom.getElementsByTagName("*"):
                    if not elem.hasAttribute("w16cid:durableId"):
                        continue

                    durable_id = elem.getAttribute("w16cid:durableId")
                    needs_repair = False

                    if xml_file.name == "numbering.xml":
                        try:
                            needs_repair = self._parse_id_value(durable_id, base=10) >= 0x7FFFFFFF
                        except ValueError:
                            needs_repair = True
                    else:
                        try:
                            needs_repair = self._parse_id_value(durable_id, base=16) >= 0x7FFFFFFF
                        except ValueError:
                            needs_repair = True

                    if needs_repair:
                        value = random.randint(1, 0x7FFFFFFE)
                        new_id = str(value) if xml_file.name == "numbering.xml" else f"{value:08X}"
                        elem.setAttribute("w16cid:durableId", new_id)
                        print(f"  Repaired: {xml_file.name}: durableId {durable_id} → {new_id}")
                        repairs += 1
                        modified = True

                if modified:
                    xml_file.write_bytes(dom.toxml(encoding="UTF-8"))

            except Exception:
                pass

        return repairs


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
