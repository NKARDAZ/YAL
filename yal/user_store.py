"""
Дополнение к store.py — функции для пользовательских шаблонов.

Пользовательские шаблоны хранятся в:
  ~/.yal/user-templates/<kind>/<name>/<version>/

Метаданные — в <version>/yal-meta.json (тот же формат, что у встроенных).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

YAL_HOME = Path.home() / ".yal"
USER_TEMPLATES_DIR = YAL_HOME / "user-templates"


def user_template_dir(kind: str, name: str, version: str) -> Path:
    return USER_TEMPLATES_DIR / kind / name / version


def user_meta_path(kind: str, name: str, version: str) -> Path:
    return user_template_dir(kind, name, version) / "yal-meta.json"


def user_is_installed(kind: str, name: str, version: str) -> bool:
    return user_meta_path(kind, name, version).exists()


def user_installed_versions(kind: str, name: str) -> list[str]:
    base = USER_TEMPLATES_DIR / kind / name
    if not base.exists():
        return []
    return [
        p.name for p in base.iterdir()
        if p.is_dir() and (p / "yal-meta.json").exists()
    ]


def user_get_most_recent_local(kind: str, name: str) -> str | None:
    versions = user_installed_versions(kind, name)
    if not versions:
        return None
    versions.sort(
        key=lambda v: user_template_dir(kind, name, v).stat().st_mtime,
        reverse=True,
    )
    return versions[0]


def user_latest_release_version(kind: str, name: str) -> str | None:
    versions = [v for v in user_installed_versions(kind, name) if not _looks_like_commit(v)]
    if not versions:
        return None

    def _key(v: str):
        try:
            return tuple(int(x) for x in v.lstrip("vV").split("."))
        except ValueError:
            return (0,)

    return sorted(versions, key=_key)[-1]


def user_save_meta(
    kind: str,
    name: str,
    version: str,
    source: Literal["release", "commit"],
    repo: str,
) -> None:
    p = user_meta_path(kind, name, version)
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


def user_remove(kind: str, name: str, version: str) -> None:
    d = user_template_dir(kind, name, version)
    if d.exists():
        shutil.rmtree(d)


def _looks_like_commit(s: str) -> bool:
    return len(s) == 7 and all(c in "0123456789abcdef" for c in s.lower())
