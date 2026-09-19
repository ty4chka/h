"""L3 — security scanner: статический анализ исходника модуля (AST).

Не выполняет код. Помечает опасные вызовы до загрузки: exec/eval,
os.system, subprocess, __import__ с динамическим аргументом.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List


class SecurityError(Exception):
    """Загрузка запрещена политикой безопасности."""


@dataclass
class Finding:
    rule: str
    lineno: int
    detail: str
    severity: str = "critical"  # critical | warn


def scan_source(source: str) -> List[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [Finding("syntax", e.lineno or 0, str(e))]

    findings: List[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in ("exec", "eval", "__import__"):
                findings.append(
                    Finding(fn.id, node.lineno, f"вызов {fn.id}()")
                )
            elif (
                isinstance(fn, ast.Attribute)
                and fn.attr == "system"
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "os"
            ):
                findings.append(Finding("os.system", node.lineno, "вызов os.system()"))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = node.module if isinstance(node, ast.ImportFrom) else None
            names = [a.name for a in node.names]
            if mod == "subprocess" or "subprocess" in names:
                findings.append(Finding("subprocess", node.lineno, "импорт subprocess"))
            if isinstance(node, ast.ImportFrom) and mod == "shutil" and "rmtree" in names:
                findings.append(
                    Finding("shutil.rmtree", node.lineno, "импорт shutil.rmtree", severity="warn")
                )
    return findings
