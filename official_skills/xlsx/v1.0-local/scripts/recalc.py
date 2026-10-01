"""通过 LibreOffice 重新计算 Excel 文件中的所有公式"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from office.soffice import get_soffice_env
from openpyxl import load_workbook

_MACRO_DIRS = {
    "Darwin": "~/Library/Application Support/LibreOffice/4/user/basic/Standard",
    "Linux": "~/.config/libreoffice/4/user/basic/Standard",
}
_MACRO_FILENAME = "Module1.xba"

_RECALCULATE_MACRO = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
    Sub RecalculateAndSave()
      ThisComponent.calculateAll()
      ThisComponent.store()
      ThisComponent.close(True)
    End Sub
</script:module>"""

_EXCEL_ERRORS = ("#VALUE!", "#DIV/0!", "#REF!", "#NAME?", "#NULL!", "#NUM!", "#N/A")


def _gtimeout_available() -> bool:
    try:
        subprocess.run(["gtimeout", "--version"], capture_output=True, timeout=1, check=False)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _setup_macro() -> bool:
    system = platform.system()
    macro_dir = Path(os.path.expanduser(_MACRO_DIRS.get(system, _MACRO_DIRS["Linux"])))
    macro_file = macro_dir / _MACRO_FILENAME

    if macro_file.exists() and "RecalculateAndSave" in macro_file.read_text():
        return True

    if not macro_dir.exists():
        subprocess.run(
            ["soffice", "--headless", "--terminate_after_init"],
            capture_output=True, timeout=10, env=get_soffice_env(),
        )
        macro_dir.mkdir(parents=True, exist_ok=True)

    try:
        macro_file.write_text(_RECALCULATE_MACRO)
        return True
    except Exception:
        return False


def _build_command(abs_path: str, timeout: int) -> list[str]:
    cmd = [
        "soffice", "--headless", "--norestore",
        "vnd.sun.star.script:Standard.Module1.RecalculateAndSave?language=Basic&location=application",
        abs_path,
    ]
    system = platform.system()
    if system == "Linux":
        cmd = ["timeout", str(timeout)] + cmd
    elif system == "Darwin" and _gtimeout_available():
        cmd = ["gtimeout", str(timeout)] + cmd
    return cmd


def _scan_errors(filepath: str) -> dict:
    wb = load_workbook(filepath, data_only=True)
    error_details = {err: [] for err in _EXCEL_ERRORS}
    total = 0

    for name in wb.sheetnames:
        for row in wb[name].iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    for err in _EXCEL_ERRORS:
                        if err in cell.value:
                            error_details[err].append(f"{name}!{cell.coordinate}")
                            total += 1
                            break
    wb.close()
    return error_details, total


def _count_formulas(filepath: str) -> int:
    wb = load_workbook(filepath, data_only=False)
    count = sum(
        1
        for name in wb.sheetnames
        for row in wb[name].iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("=")
    )
    wb.close()
    return count


def recalc(filename: str, timeout: int = 30) -> dict:
    path = Path(filename)
    if not path.exists():
        return {"error": f"File {filename} does not exist"}

    abs_path = str(path.absolute())

    if not _setup_macro():
        return {"error": "Failed to setup LibreOffice macro"}

    cmd = _build_command(abs_path, timeout)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=get_soffice_env())

    if proc.returncode not in (0, 124):
        stderr = proc.stderr or "Unknown error during recalculation"
        if "Module1" in stderr or "RecalculateAndSave" not in stderr:
            return {"error": "LibreOffice macro not configured properly"}
        return {"error": stderr}

    try:
        error_details, total = _scan_errors(filename)

        result = {
            "status": "success" if total == 0 else "errors_found",
            "total_errors": total,
            "error_summary": {
                err_type: {"count": len(locs), "locations": locs[:20]}
                for err_type, locs in error_details.items()
                if locs
            },
            "total_formulas": _count_formulas(filename),
        }
        return result

    except Exception as e:
        return {"error": str(e)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python recalc.py <excel_file> [timeout_seconds]")
        print("\nRecalculates all formulas in an Excel file using LibreOffice")
        print("\nReturns JSON with error details:")
        print("  - status: 'success' or 'errors_found'")
        print("  - total_errors: Total number of Excel errors found")
        print("  - total_formulas: Number of formulas in the file")
        print("  - error_summary: Breakdown by error type with locations")
        print("    - #VALUE!, #DIV/0!, #REF!, #NAME?, #NULL!, #NUM!, #N/A")
        sys.exit(1)

    filename = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    result = recalc(filename, timeout)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
