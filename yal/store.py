"""
Хранилище скачанных шаблонов.

Структура на диске:
  ~/.yal/templates/<kind>/<name>/<version>/   — релиз или коммит
  ~/.yal/templates/<kind>/<name>/<sha7>/      — если версия — это коммит

Метаданные каждого шаблона хранятся в <version>/yal-meta.json:
  {
    "kind":    "book",
    "name":    "default",
    "version": "1.7.1",          # тег релиза ИЛИ полный sha коммита
    "source":  "release|commit",
    "repo":    "https://github.com/...",
    "installed_at": "2025-01-01T00:00:00"
  }
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

YAL_HOME = Path.home() / ".yal"
TEMPLATES_DIR = YAL_HOME / "templates"


def template_dir(kind: str, name: str, version: str) -> Path:
    """Полный путь к папке конкретного шаблона."""
    return TEMPLATES_DIR / kind / name / version


def meta_path(kind: str, name: str, version: str) -> Path:
    return template_dir(kind, name, version) / "yal-meta.json"


def get_most_recent_local(kind: str, name: str) -> str | None:
    """Возвращает версию самого свежего установленного шаблона."""
    versions = installed_versions(kind, name)
    if not versions:
        return None
    versions.sort(key=lambda v: template_dir(kind, name, v).stat().st_mtime, reverse=True)
    return versions[0]


def is_installed(kind: str, name: str, version: str) -> bool:
    return meta_path(kind, name, version).exists()


def installed_versions(kind: str, name: str) -> list[str]:
    """Возвращает список установленных версий (теги + sha)."""
    base = TEMPLATES_DIR / kind / name
    if not base.exists():
        return []
    return [p.name for p in base.iterdir() if p.is_dir() and (p / "yal-meta.json").exists()]


def latest_release_version(kind: str, name: str) -> str | None:
    """
    Возвращает «наибольшую» установленную версию-релиз (по semver-like сортировке).
    Коммиты (7-символьные hex) пропускаются.
    """
    versions = [v for v in installed_versions(kind, name) if not _looks_like_commit(v)]
    if not versions:
        return None

    def _key(v: str):
        try:
            return tuple(int(x) for x in v.lstrip("vV").split("."))
        except ValueError:
            return (0,)

    return sorted(versions, key=_key)[-1]


def best_local_version(kind: str, name: str, ref: str | None) -> str | None:
    """
    Выбирает лучшую локальную версию под запрос ref.
    ref=None или "latest" → самый свежий релиз, иначе коммиты
    ref="1.7.1"           → конкретный тег
    ref="c651f7d"         → конкретный sha
    """
    if ref is None or ref == "latest":
        return latest_release_version(kind, name)
    if is_installed(kind, name, ref):
        return ref
    return None


def save_meta(
    kind: str,
    name: str,
    version: str,
    source: Literal["release", "commit"],
    repo: str,
) -> None:
    p = meta_path(kind, name, version)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "kind": kind,
                "name": name,
                "version": version,
                "source": source,
                "repo": repo,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def remove(kind: str, name: str, version: str) -> None:
    d = template_dir(kind, name, version)
    if d.exists():
        shutil.rmtree(d)


def _looks_like_commit(s: str) -> bool:
    """True, если строка похожа на короткий sha коммита (7 hex-символов)."""
    return len(s) == 7 and all(c in "0123456789abcdef" for c in s.lower())
