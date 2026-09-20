# utils/security.py
# Безопасное распаковывание архивов (защита от path traversal / zip-slip).
from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path
from typing import Union


def _safe_dest(dest: Union[str, Path]) -> Path:
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _check_member(name: str, dest: Path) -> None:
    target = (dest / name).resolve()
    if not str(target).startswith(str(dest) + os.sep) and target != dest:
        raise ValueError(f"небезопасный путь в архиве: {name}")


def safe_extract_zip(archive: Union[str, Path, bytes], dest: Union[str, Path]) -> Path:
    """Распаковать zip, отклоняя записи с выходом за dest."""
    dest = _safe_dest(dest)
    if isinstance(archive, (bytes, bytearray)):
        import io

        zf = zipfile.ZipFile(io.BytesIO(archive))
    else:
        zf = zipfile.ZipFile(archive)
    with zf:
        for info in zf.infolist():
            _check_member(info.filename, dest)
        zf.extractall(dest)
    return dest


def safe_extract_archive(archive: Union[str, Path], dest: Union[str, Path]) -> Path:
    """Распаковать tar/zip-архив безопасно (по расширению)."""
    path = str(archive)
    if path.lower().endswith(".zip"):
        return safe_extract_zip(path, dest)
    dest = _safe_dest(dest)
    with tarfile.open(path) as tf:
        for member in tf.getmembers():
            _check_member(member.name, dest)
            if member.issym() or member.islnk():
                raise ValueError(f"ссылки в архиве запрещены: {member.name}")
        tf.extractall(dest)
    return dest


def safe_extract_tar(archive: Union[str, Path], dest: Union[str, Path]) -> Path:
    """Распаковать tar-архив безопасно (как в MCUB-fork utils.security)."""
    dest = _safe_dest(dest)
    with tarfile.open(str(archive)) as tf:
        for member in tf.getmembers():
            _check_member(member.name, dest)
            if member.issym() or member.islnk():
                raise ValueError(f"ссылки в архиве запрещены: {member.name}")
        tf.extractall(dest)
    return dest


def get_db_path(api_id: int | None = None, api_hash: str | None = None) -> str:
    """Путь к БД юзербота (utils.security.get_db_path из MCUB-fork).

    В Hydra хранилище живёт в data/db; возвращаем путь к общему файлу,
    чтобы MCUB-модули могли открыть sqlite напрямую при желании.
    """
    base = Path("data/db")
    base.mkdir(parents=True, exist_ok=True)
    if api_id and api_hash:
        return str(base / f"userbot_{api_id}.db")
    return str(base / "userbot.db")


__all__ = [
    "safe_extract_zip",
    "safe_extract_archive",
    "safe_extract_tar",
    "get_db_path",
]
