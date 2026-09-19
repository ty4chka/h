"""L3 — manifest: метаданные модуля из комментария `# meta: ...`.

Пример строки в шапке файла:
    # meta: name=ping version=1.2.0 requires=db,utils framework=mcub
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

_META_RE = re.compile(r"^#\s*meta:\s*(?P<body>.+?)\s*$", re.MULTILINE)
_KV_RE = re.compile(r"(\w+)=([^\s]+)")


@dataclass
class Manifest:
    name: str
    version: str = "0.0.0"
    requires: List[str] = field(default_factory=list)
    framework: str = "auto"


def parse_manifest(default_name: str, source: str) -> Manifest:
    m = _META_RE.search(source)
    man = Manifest(name=default_name)
    if not m:
        return man
    for key, value in _KV_RE.findall(m.group("body")):
        if key == "name":
            man.name = value
        elif key == "version":
            man.version = value
        elif key == "requires":
            man.requires = [x for x in value.split(",") if x]
        elif key == "framework":
            man.framework = value
    return man
