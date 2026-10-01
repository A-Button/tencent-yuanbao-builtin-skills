"""
针对 XSD 模式对 PowerPoint 演示文稿 XML 文件进行校验的验证器。
"""

import re

from .base import BaseSchemaValidator


class PPTXSchemaValidator(BaseSchemaValidator):
    """用于验证 PPTX (PowerPoint) 文件结构与内容完整性的模式验证器。"""

    PRESENTATIONML_NAMESPACE = (
        "http://schemas.openxmlformats.org/presentationml/2006/main"
    )

    ELEMENT_RELATIONSHIP_TYPES = {
        "sldid": "slide",
        "sldmasterid": "slidemaster",
        "notesmasterid": "notesmaster",
        "sldlayoutid": "slidelayout",
        "themeid": "theme",
        "tablestyleid": "tablestyles",
    }

    def validate(self):
        """
        执行所有 PPTX 验证检查。

        依次运行 XML 格式验证、命名空间验证、ID 唯一性验证、UUID 格式验证、
        文件引用验证、幻灯片布局 ID 验证、内容类型验证、XSD 模式验证、
        备注幻灯片引用验证、关系 ID 验证以及重复幻灯片布局检测。

        返回:
            bool: 所有验证均通过时返回 True，否则返回 False。
        """
        if not self.validate_xml():
            return False

        checks = [
            self.validate_namespaces,
            self.validate_unique_ids,
            self.validate_uuid_ids,
            self.validate_file_references,
            self.validate_slide_layout_ids,
            self.validate_content_types,
            self.validate_against_xsd,
            self.validate_notes_slide_references,
            self.validate_all_relationship_ids,
            self.validate_no_duplicate_slide_layouts,
        ]
        results = [check() for check in checks]
        return all(results)

    def validate_uuid_ids(self):
        """
        验证所有类似 UUID 的 ID 属性是否包含合法的十六进制字符。

        遍历所有 XML 文件中的元素属性，检测名称以 'id' 结尾的属性值。
        如果该值看起来像 UUID（去除括号和连字符后恰好 32 个字母数字字符），
        则进一步验证其是否符合标准 UUID 十六进制格式。

        返回:
            bool: 所有 UUID 类 ID 均合法时返回 True，否则返回 False。
        """
        import lxml.etree

        uuid_re = re.compile(
            r"^[\{\(]?[0-9A-Fa-f]{8}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}"
            r"-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{12}[\}\)]?$"
        )
        found_errors = []

        for xml_path in self.xml_files:
            try:
                tree = lxml.etree.parse(str(xml_path))
                root_elem = tree.getroot()

                for node in root_elem.iter():
                    for attr_key, attr_val in node.attrib.items():
                        local_name = attr_key.split("}")[-1].lower()
                        if local_name != "id" and not local_name.endswith("id"):
                            continue
                        if not self._is_uuid_format(attr_val):
                            continue
                        if uuid_re.match(attr_val):
                            continue
                        found_errors.append(
                            f"  {xml_path.relative_to(self.unpacked_dir)}: "
                            f"Line {node.sourceline}: ID '{attr_val}' appears to be a UUID but contains invalid hex characters"
                        )

            except (lxml.etree.XMLSyntaxError, Exception) as exc:
                found_errors.append(
                    f"  {xml_path.relative_to(self.unpacked_dir)}: Error: {exc}"
                )

        if found_errors:
            print(f"FAILED - Found {len(found_errors)} UUID ID validation errors:")
            for msg in found_errors:
                print(msg)
            return False

        if self.verbose:
            print("PASSED - All UUID-like IDs contain valid hex values")
        return True

    def _is_uuid_format(self, value):
        """
        判断给定字符串是否具有 UUID 的外观特征。

        去除首尾的花括号或圆括号以及连字符后，检查剩余内容是否恰好
        为 32 个字母数字字符。

        参数:
            value: 待检测的字符串。

        返回:
            bool: 符合 UUID 外观特征时返回 True。
        """
        stripped = value.strip("{}()").replace("-", "")
        return len(stripped) == 32 and stripped.isalnum()

    def validate_slide_layout_ids(self):
        """
        验证幻灯片母版中引用的布局 ID 是否在关系文件中存在对应条目。

        遍历所有幻灯片母版 XML 文件，提取其中的 sldLayoutId 元素，
        并与对应 .rels 关系文件中声明的 slideLayout 关系进行比对。
        若某个 sldLayoutId 引用的 r:id 在关系文件中找不到，则报错。

        返回:
            bool: 所有布局 ID 引用均有效时返回 True，否则返回 False。
        """
        import lxml.etree

        found_errors = []
        master_files = sorted(self.unpacked_dir.glob("ppt/slideMasters/*.xml"))

        if not master_files:
            if self.verbose:
                print("PASSED - No slide masters found")
            return True

        for master_path in master_files:
            try:
                master_root = lxml.etree.parse(str(master_path)).getroot()

                rels_path = master_path.parent / "_rels" / f"{master_path.name}.rels"
                if not rels_path.exists():
                    found_errors.append(
                        f"  {master_path.relative_to(self.unpacked_dir)}: "
                        f"Missing relationships file: {rels_path.relative_to(self.unpacked_dir)}"
                    )
                    continue

                rels_root = lxml.etree.parse(str(rels_path)).getroot()

                layout_rid_set = set()
                ns_pkg = self.PACKAGE_RELATIONSHIPS_NAMESPACE
                for rel_elem in rels_root.findall(f".//{{{ns_pkg}}}Relationship"):
                    if "slideLayout" in rel_elem.get("Type", ""):
                        layout_rid_set.add(rel_elem.get("Id"))

                ns_pml = self.PRESENTATIONML_NAMESPACE
                ns_rel = self.OFFICE_RELATIONSHIPS_NAMESPACE
                for layout_id_elem in master_root.findall(
                    f".//{{{ns_pml}}}sldLayoutId"
                ):
                    rid_value = layout_id_elem.get(f"{{{ns_rel}}}id")
                    numeric_id = layout_id_elem.get("id")

                    if rid_value and rid_value not in layout_rid_set:
                        found_errors.append(
                            f"  {master_path.relative_to(self.unpacked_dir)}: "
                            f"Line {layout_id_elem.sourceline}: sldLayoutId with id='{numeric_id}' "
                            f"references r:id='{rid_value}' which is not found in slide layout relationships"
                        )

            except (lxml.etree.XMLSyntaxError, Exception) as exc:
                found_errors.append(
                    f"  {master_path.relative_to(self.unpacked_dir)}: Error: {exc}"
                )

        if found_errors:
            print(
                f"FAILED - Found {len(found_errors)} slide layout ID validation errors:"
            )
            for msg in found_errors:
                print(msg)
            print(
                "Remove invalid references or add missing slide layouts to the relationships file."
            )
            return False

        if self.verbose:
            print("PASSED - All slide layout IDs reference valid slide layouts")
        return True

    def validate_no_duplicate_slide_layouts(self):
        """
        检测是否存在幻灯片同时引用了多个 slideLayout 的情况。

        每张幻灯片的 .rels 关系文件中应当仅包含一个 slideLayout 类型的关系。
        本方法扫描所有幻灯片关系文件，若发现任何文件包含多于一个
        slideLayout 引用，则视为错误。

        返回:
            bool: 所有幻灯片均只有单一布局引用时返回 True，否则返回 False。
        """
        import lxml.etree

        found_errors = []
        rels_file_list = sorted(
            self.unpacked_dir.glob("ppt/slides/_rels/*.xml.rels")
        )

        ns_pkg = self.PACKAGE_RELATIONSHIPS_NAMESPACE
        for rels_path in rels_file_list:
            try:
                root = lxml.etree.parse(str(rels_path)).getroot()

                layout_count = sum(
                    1
                    for rel in root.findall(f".//{{{ns_pkg}}}Relationship")
                    if "slideLayout" in rel.get("Type", "")
                )

                if layout_count > 1:
                    found_errors.append(
                        f"  {rels_path.relative_to(self.unpacked_dir)}: "
                        f"has {layout_count} slideLayout references"
                    )

            except Exception as exc:
                found_errors.append(
                    f"  {rels_path.relative_to(self.unpacked_dir)}: Error: {exc}"
                )

        if found_errors:
            print("FAILED - Found slides with duplicate slideLayout references:")
            for msg in found_errors:
                print(msg)
            return False

        if self.verbose:
            print("PASSED - All slides have exactly one slideLayout reference")
        return True

    def validate_notes_slide_references(self):
        """
        验证备注幻灯片的引用唯一性，确保每个备注幻灯片仅被一张幻灯片引用。

        扫描所有幻灯片关系文件，收集 notesSlide 类型的引用目标，
        并检测是否有多张幻灯片引用了同一个备注幻灯片文件。

        返回:
            bool: 所有备注幻灯片引用均唯一时返回 True，否则返回 False。
        """
        import lxml.etree

        found_errors = []
        notes_ref_map = {}

        rels_file_list = sorted(
            self.unpacked_dir.glob("ppt/slides/_rels/*.xml.rels")
        )

        if not rels_file_list:
            if self.verbose:
                print("PASSED - No slide relationship files found")
            return True

        ns_pkg = self.PACKAGE_RELATIONSHIPS_NAMESPACE
        for rels_path in rels_file_list:
            try:
                root = lxml.etree.parse(str(rels_path)).getroot()

                for rel_elem in root.findall(f".//{{{ns_pkg}}}Relationship"):
                    if "notesSlide" not in rel_elem.get("Type", ""):
                        continue
                    target_val = rel_elem.get("Target", "")
                    if not target_val:
                        continue

                    normalized = target_val.replace("../", "")
                    slide_name = rels_path.stem.replace(".xml", "")

                    notes_ref_map.setdefault(normalized, []).append(
                        (slide_name, rels_path)
                    )

            except (lxml.etree.XMLSyntaxError, Exception) as exc:
                found_errors.append(
                    f"  {rels_path.relative_to(self.unpacked_dir)}: Error: {exc}"
                )

        for target_key, ref_list in notes_ref_map.items():
            if len(ref_list) <= 1:
                continue
            slide_names = [entry[0] for entry in ref_list]
            found_errors.append(
                f"  Notes slide '{target_key}' is referenced by multiple slides: "
                f"{', '.join(slide_names)}"
            )
            for sname, rpath in ref_list:
                found_errors.append(
                    f"    - {rpath.relative_to(self.unpacked_dir)}"
                )

        if found_errors:
            top_level_count = len(
                [e for e in found_errors if not e.startswith("    ")]
            )
            print(
                f"FAILED - Found {top_level_count} notes slide reference validation errors:"
            )
            for msg in found_errors:
                print(msg)
            print("Each slide may optionally have its own slide file.")
            return False

        if self.verbose:
            print("PASSED - All notes slide references are unique")
        return True


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
