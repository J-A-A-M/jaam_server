"""Рендерить markdown-таблицю результатів тестів у GITHUB_STEP_SUMMARY.

Читає:
- admin_panel/frontend/vitest-results.json (Vitest, Jest-сумісний JSON)
- pytest-results.xml (pytest JUnit)
- env TYPECHECK — outcome кроку typecheck ('success'/'failure')

Пише markdown у stdout (крок редіректить його у $GITHUB_STEP_SUMMARY).
"""

import json
import os
import xml.etree.ElementTree as ET


def frontend_unit() -> tuple[int, int, bool]:
    d = json.load(open("admin_panel/frontend/vitest-results.json"))
    passed = int(d.get("numPassedTests", 0))
    failed = int(d.get("numFailedTests", 0))
    ok = bool(d.get("success", failed == 0)) and failed == 0
    return passed, failed, ok


def backend_unit() -> tuple[int, int, bool]:
    root = ET.parse("pytest-results.xml").getroot()
    ts = root if root.tag == "testsuite" else root.find("testsuite")
    tests = int(ts.get("tests", 0))
    bad = int(ts.get("failures", 0)) + int(ts.get("errors", 0))
    return tests - bad, bad, bad == 0


def main() -> None:
    rows = []

    tc_ok = os.environ.get("TYPECHECK") == "success"
    rows.append(("Frontend typecheck", "—", "—", "✅" if tc_ok else "❌"))

    for label, fn in (("Frontend unit (Vitest)", frontend_unit), ("Backend unit (pytest)", backend_unit)):
        try:
            passed, failed, ok = fn()
            rows.append((label, str(passed), str(failed), "✅" if ok else "❌"))
        except Exception as exc:  # noqa: BLE001
            rows.append((label, "?", "?", f"❌ ({exc})"))

    out = ["## 🧪 Результати тестів адмін-панелі", ""]
    out.append("| Набір | ✅ Passed | ❌ Failed | Статус |")
    out.append("|-------|----------:|----------:|:------:|")
    for name, passed, failed, status in rows:
        out.append(f"| {name} | {passed} | {failed} | {status} |")
    out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main()
