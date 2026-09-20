"""L3 — loader: загрузка модулей из исходника/каталога через адаптеры L2.

Порядок действий: security scan -> manifest -> resolver (для каталогов) ->
адаптер фреймворка -> lifecycle -> registry.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .manifest import Manifest, parse_manifest
from .registry import Record, Registry
from .resolver import resolve
from .scanner import scan_source, SecurityError
from ..api.module_base import ModuleBase

logger = logging.getLogger("hydra_kernel.loader")

_ADAPTERS = {
    "mcub": "hydra_kernel.compat.mcub.McubAdapter",
    "hikka": "hydra_kernel.compat.frameworks.HikkaAdapter",
    "heroku": "hydra_kernel.compat.frameworks.HerokuAdapter",
    "dragon": "hydra_kernel.compat.frameworks.DragonAdapter",
    "setup": "hydra_kernel.compat.core_style.SetupAdapter",
    "core": "hydra_kernel.compat.core_style.CoreStyleAdapter",
    "noop": "hydra_kernel.compat.core_style.NoopAdapter",
}


def detect_framework(source: str) -> str:
    """Автоопределение стиля модуля, когда нет `# meta: framework=...`."""
    if "hydra_kernel" in source:
        return "hydra"
    if re.search(r"^def setup\(client", source, re.M):
        return "setup"
    if re.search(r"^def register\(kernel", source, re.M) or re.search(
        r"^ {0,4}from core\.lib\.loader", source, re.M
    ):
        return "mcub"
    if re.search(r"^async def \w+_handler\(", source, re.M):
        return "core"
    return "noop"


class Loader:
    def __init__(self, hydra: Any):
        self.h = hydra
        self._adapters: Dict[str, Any] = {}

    def adapter_for(self, framework: str) -> Any:
        if framework not in _ADAPTERS:
            raise ValueError(f"неизвестный фреймворк: {framework}")
        if framework not in self._adapters:
            import importlib

            mod_path, cls_name = _ADAPTERS[framework].rsplit(".", 1)
            cls = getattr(importlib.import_module(mod_path), cls_name)
            adapter = cls(self.h)
            adapter.install()
            self._adapters[framework] = adapter
        return self._adapters[framework]

    async def load_source(
        self,
        name: str,
        source: str,
        framework: str = "auto",
        allow_unsafe: bool = False,
        file_path: Optional[str] = None,
    ) -> Record:
        findings = scan_source(source)
        critical = [f for f in findings if f.severity == "critical"]
        if critical and not allow_unsafe:
            raise SecurityError(
                f"{name}: " + "; ".join(f"{f.rule}@{f.lineno}" for f in critical)
            )

        manifest = parse_manifest(name, source)
        fw = framework if framework != "auto" else manifest.framework
        if fw == "auto":
            fw = detect_framework(source)

        if fw == "hydra":
            module, lifecycle = await self._load_hydra(name, source, file_path)
        else:
            adapter = self.adapter_for(fw)
            # file_path нужен MCUB-адаптеру: по нему строится spec модуля и
            # __path__ для относительных импортов (CubKit-сборки).
            module, lifecycle = await adapter.load_source(
                name, source, file_path=file_path
            )

        record = Record(
            name=manifest.name, module=module, manifest=manifest, framework=fw, lifecycle=lifecycle
        )
        self.h.registry.register(record)
        logger.info("loaded %s [%s]", manifest.name, fw)
        return record

    async def load_dir(
        self,
        path: str | Path,
        framework: str = "auto",
        allow_unsafe: bool = False,
        exclude: Tuple[str, ...] = (),
    ) -> Tuple[List[Record], List[Tuple[str, Exception]]]:
        """Загружает каталог модулей волнами: параллельно внутри уровня зависимостей."""
        import asyncio

        files = [p for p in sorted(Path(path).glob("*.py")) if p.stem not in exclude]
        sources = {p.stem: p.read_text(encoding="utf-8") for p in files}
        manifests = {stem: parse_manifest(stem, src) for stem, src in sources.items()}
        order = resolve(manifests)

        records: List[Record] = []
        errors: List[Tuple[str, Exception]] = []
        loaded: set = set()
        remaining = list(order)

        async def _one(stem: str) -> Record:
            file = next(p for p in files if p.stem == stem)
            return await self.load_source(
                stem,
                sources[stem],
                framework=framework,
                allow_unsafe=allow_unsafe,
                file_path=str(file),
            )

        while remaining:
            wave = [
                s for s in remaining
                if all(
                    r in loaded or r not in manifests
                    for r in getattr(manifests[s], "requires", ()) or ()
                )
            ] or remaining[:]
            results = await asyncio.gather(
                *(_one(s) for s in wave), return_exceptions=True
            )
            for stem, res in zip(wave, results):
                if isinstance(res, Exception):
                    logger.error(
                        "failed to load %s: %s",
                        stem,
                        res,
                        exc_info=(type(res), res, res.__traceback__),
                    )
                    errors.append((stem, res))
                else:
                    records.append(res)
                    loaded.add(stem)
            done = set(wave)
            remaining = [s for s in remaining if s not in done]
        return records, errors

    async def unload(self, name: str) -> bool:
        record = self.h.registry.unregister(name)
        if record is None:
            return False
        if record.lifecycle is not None:
            await record.lifecycle.unload(record.module)
        return True

    # -- приватное --

    async def _load_hydra(self, name: str, source: str, file_path: Optional[str] = None) -> Tuple[ModuleBase, Any]:
        code = compile(source, str(file_path or f"<hydra:{name}>"), "exec")
        ns: Dict[str, Any] = {"__name__": name, "__file__": str(file_path or f"<hydra:{name}>")}
        exec(code, ns)  # noqa: S102 — модуль прошёл scanner

        cls = None
        for value in ns.values():
            if (
                isinstance(value, type)
                and issubclass(value, ModuleBase)
                and value is not ModuleBase
                and getattr(value, "__module__", "") == name
            ):
                cls = value
                break
        if cls is None:
            raise ValueError(f"{name}: нет подкласса ModuleBase")

        module = cls(self.h.make_context(name))
        lifecycle = await self.h.load_module(module)
        return module, lifecycle
