"""PowerPoint 演示文稿 XML 文件的 XSD schema 验证器。"""

import re

from .base import BaseSchemaValidator


class PPTXSchemaValidator(BaseSchemaValidator):

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

        return all(check() for check in checks)

    def validate_uuid_ids(self):
        import lxml.etree

        errors = []
        uuid_re = re.compile(
            r"^[\{\(]?[0-9A-Fa-f]{8}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{12}[\}\)]?$"
        )

        for xml_file in self.xml_files:
            try:
                root = lxml.etree.parse(str(xml_file)).getroot()

                for elem in root.iter():
                    for attr, value in elem.attrib.items():
                        attr_name = attr.split("}")[-1].lower()
                        if attr_name == "id" or attr_name.endswith("id"):
                            if self._looks_like_uuid(value) and not uuid_re.match(value):
                                errors.append(
                                    f"  {xml_file.relative_to(self.unpacked_dir)}: "
                                    f"Line {elem.sourceline}: ID '{value}' appears to be a UUID but contains invalid hex characters"
                                )

            except (lxml.etree.XMLSyntaxError, Exception) as e:
                errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {e}")

        if errors:
            print(f"FAILED - Found {len(errors)} UUID ID validation errors:")
            for err in errors:
                print(err)
            return False

        if self.verbose:
            print("PASSED - All UUID-like IDs contain valid hex values")
        return True

    def _looks_like_uuid(self, value):
        clean = value.strip("{}()").replace("-", "")
        return len(clean) == 32 and all(c.isalnum() for c in clean)

    def validate_slide_layout_ids(self):
        import lxml.etree

        errors = []
        slide_masters = list(self.unpacked_dir.glob("ppt/slideMasters/*.xml"))

        if not slide_masters:
            if self.verbose:
                print("PASSED - No slide masters found")
            return True

        for sm in slide_masters:
            try:
                root = lxml.etree.parse(str(sm)).getroot()
                rels_file = sm.parent / "_rels" / f"{sm.name}.rels"

                if not rels_file.exists():
                    errors.append(
                        f"  {sm.relative_to(self.unpacked_dir)}: "
                        f"Missing relationships file: {rels_file.relative_to(self.unpacked_dir)}"
                    )
                    continue

                rels_root = lxml.etree.parse(str(rels_file)).getroot()
                valid_layout_rids = {
                    rel.get("Id")
                    for rel in rels_root.findall(
                        f".//{{{self.PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship"
                    )
                    if "slideLayout" in rel.get("Type", "")
                }

                for sld_layout in root.findall(
                    f".//{{{self.PRESENTATIONML_NAMESPACE}}}sldLayoutId"
                ):
                    r_id = sld_layout.get(f"{{{self.OFFICE_RELATIONSHIPS_NAMESPACE}}}id")
                    layout_id = sld_layout.get("id")

                    if r_id and r_id not in valid_layout_rids:
                        errors.append(
                            f"  {sm.relative_to(self.unpacked_dir)}: "
                            f"Line {sld_layout.sourceline}: sldLayoutId with id='{layout_id}' "
                            f"references r:id='{r_id}' which is not found in slide layout relationships"
                        )

            except (lxml.etree.XMLSyntaxError, Exception) as e:
                errors.append(f"  {sm.relative_to(self.unpacked_dir)}: Error: {e}")

        if errors:
            print(f"FAILED - Found {len(errors)} slide layout ID validation errors:")
            for err in errors:
                print(err)
            print("Remove invalid references or add missing slide layouts to the relationships file.")
            return False

        if self.verbose:
            print("PASSED - All slide layout IDs reference valid slide layouts")
        return True

    def validate_no_duplicate_slide_layouts(self):
        import lxml.etree

        errors = []
        slide_rels = list(self.unpacked_dir.glob("ppt/slides/_rels/*.xml.rels"))

        for rels_file in slide_rels:
            try:
                root = lxml.etree.parse(str(rels_file)).getroot()

                layout_count = sum(
                    1
                    for rel in root.findall(
                        f".//{{{self.PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship"
                    )
                    if "slideLayout" in rel.get("Type", "")
                )

                if layout_count > 1:
                    errors.append(
                        f"  {rels_file.relative_to(self.unpacked_dir)}: has {layout_count} slideLayout references"
                    )

            except Exception as e:
                errors.append(f"  {rels_file.relative_to(self.unpacked_dir)}: Error: {e}")

        if errors:
            print("FAILED - Found slides with duplicate slideLayout references:")
            for err in errors:
                print(err)
            return False

        if self.verbose:
            print("PASSED - All slides have exactly one slideLayout reference")
        return True

    def validate_notes_slide_references(self):
        import lxml.etree

        errors = []
        notes_refs = {}

        slide_rels = list(self.unpacked_dir.glob("ppt/slides/_rels/*.xml.rels"))

        if not slide_rels:
            if self.verbose:
                print("PASSED - No slide relationship files found")
            return True

        for rels_file in slide_rels:
            try:
                root = lxml.etree.parse(str(rels_file)).getroot()

                for rel in root.findall(
                    f".//{{{self.PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship"
                ):
                    if "notesSlide" not in rel.get("Type", ""):
                        continue

                    target = rel.get("Target", "")
                    if not target:
                        continue

                    normalized = target.replace("../", "")
                    slide_name = rels_file.stem.replace(".xml", "")

                    notes_refs.setdefault(normalized, []).append((slide_name, rels_file))

            except (lxml.etree.XMLSyntaxError, Exception) as e:
                errors.append(f"  {rels_file.relative_to(self.unpacked_dir)}: Error: {e}")

        for target, refs in notes_refs.items():
            if len(refs) > 1:
                names = [r[0] for r in refs]
                errors.append(
                    f"  Notes slide '{target}' is referenced by multiple slides: {', '.join(names)}"
                )
                for name, rf in refs:
                    errors.append(f"    - {rf.relative_to(self.unpacked_dir)}")

        if errors:
            non_sub = [e for e in errors if not e.startswith("    ")]
            print(f"FAILED - Found {len(non_sub)} notes slide reference validation errors:")
            for err in errors:
                print(err)
            print("Each slide may optionally have its own slide file.")
            return False

        if self.verbose:
            print("PASSED - All notes slide references are unique")
        return True


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
