"""
Пользовательский реестр шаблонов.

Хранит шаблоны, добавленные командой `yal add`, в файле
~/.yal/user-templates.toml.

Формат файла:
    [book.my-theme]
    repo    = "https://github.com/user/repo"
    exclude = ["README.md", "LICENSE"]

    [note.custom]
    repo    = "https://github.com/user/note-template"
    exclude = []

Скачанные файлы хранятся в ~/.yal/user-templates/<kind>/<name>/<version>/
отдельно от встроенных шаблонов в ~/.yal/templates/.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from yal.templates.registry import TemplateEntry

YAL_HOME = Path.home() / ".yal"
USER_REGISTRY_PATH = YAL_HOME / "user-templates.toml"

# .yal/template.toml всегда исключается глобально — нет смысла явно указывать
_GLOBAL_EXCLUDE = {".yal/template.yml"}


def load_registry() -> dict[str, dict[str, TemplateEntry]]:
    """
    Читает ~/.yal/user-templates.yml и возвращает структуру вида:
        { kind: { name: TemplateEntry(is_user=True) } }
    """
    if not USER_REGISTRY_PATH.exists():
        return {}

    with open(USER_REGISTRY_PATH, "rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    result: dict[str, dict[str, TemplateEntry]] = {}
    for raw_key, raw_val in raw.items():
        if not isinstance(raw_val, dict):
            continue

        if "::" in raw_key:
            kind, _, name = raw_key.partition("::")
            if kind not in result:
                result[kind] = {}
            meta = raw_val
            repo = meta.get("repo", "")
            if not repo:
                continue
            raw_exclude: list[str] = meta.get("exclude", [])
            exclude = _merge_exclude(raw_exclude)
            result[kind][name] = TemplateEntry(repo=repo, exclude=exclude, is_user=True)
            continue

        kind = raw_key
        names = raw_val
        if not isinstance(names, dict):
            continue
        result[kind] = {}
        for name, meta in names.items():
            if not isinstance(meta, dict):
                continue
            repo = meta.get("repo", "")
            if not repo:
                continue
            raw_exclude: list[str] = meta.get("exclude", [])
            exclude = _merge_exclude(raw_exclude)
            result[kind][name] = TemplateEntry(repo=repo, exclude=exclude, is_user=True)

    return result


def get_entry(kind: str, name: str) -> TemplateEntry | None:
    """Возвращает запись из пользовательского реестра или None. Поиск без учёта регистра."""
    registry = load_registry()
    kind_entries = registry.get(kind, {})
    name_lower = name.lower()
    for key, val in kind_entries.items():
        if key.lower() == name_lower:
            return val
    return None


def add_entry(kind: str, name: str, repo: str, exclude: list[str]) -> None:
    """
    Добавляет или обновляет запись в ~/.yal/user-templates.toml.
    .yal/template.toml в exclude не записывается (он глобальный).
    """
    YAL_HOME.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {}
    if USER_REGISTRY_PATH.exists():
        with open(USER_REGISTRY_PATH, "rb") as f:
            raw = tomllib.load(f)

    # Убираем глобальные исключения из того, что запишем явно
    clean_exclude = [e for e in exclude if e not in _GLOBAL_EXCLUDE]

    flat_key = f"{kind}::{name}"
    raw.pop(flat_key, None)
    kind_data = raw.get(kind)
    if isinstance(kind_data, dict):
        kind_data.pop(name, None)
        if not kind_data:
            raw.pop(kind, None)
    raw[flat_key] = {
        "repo": repo,
        "exclude": clean_exclude,
    }

    USER_REGISTRY_PATH.write_text(_serialize(raw), encoding="utf-8")


def remove_entry(kind: str, name: str) -> None:
    """Удаляет запись из ~/.yal/user-templates.toml. Поиск без учёта регистра."""
    if not USER_REGISTRY_PATH.exists():
        return

    with open(USER_REGISTRY_PATH, "rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    name_lower = name.lower()
    kind_data = raw.get(kind, {})
    key_to_remove = None

    if isinstance(kind_data, dict):
        key_to_remove = next((k for k in kind_data if k.lower() == name_lower), None)
        if key_to_remove is not None:
            del kind_data[key_to_remove]
            if not kind_data:
                del raw[kind]
            USER_REGISTRY_PATH.write_text(_serialize(raw), encoding="utf-8")
            return

    # Fallback for flat keys like "kind::name"
    key_to_remove = next(
        (k for k in raw if k.lower().startswith(f"{kind.lower()}::") and k.split("::", 1)[1].lower() == name_lower),
        None,
    )

    if key_to_remove is None:
        return

    del raw[key_to_remove]
    USER_REGISTRY_PATH.write_text(_serialize(raw), encoding="utf-8")


def list_kinds() -> list[str]:
    return sorted(load_registry().keys())


def list_names(kind: str) -> list[str]:
    return sorted(load_registry().get(kind, {}).keys())


# ─── вспомогательные ──────────────────────────────────────────────────────────

def _merge_exclude(raw_exclude: list[str]) -> list[str]:
    """Объединяет явные исключения с глобальными, убирает дубли и нормализует пути."""
    result: list[str] = []
    seen = set()

    # Добавляем глобальные исключения
    for item in _GLOBAL_EXCLUDE:
        normalized = item.strip("/\\")
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    # Добавляем пользовательские исключения
    for item in raw_exclude:
        normalized = item.strip("/\\")
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


def _serialize(data: dict[str, Any]) -> str:
    """Простая TOML-сериализация для структуры { kind: { name: {repo, exclude} } }."""
    lines: list[str] = []
    for kind in sorted(data):
        names = data[kind]
        if not isinstance(names, dict):
            continue
        if "::" in kind:
            meta = names
            if not isinstance(meta, dict):
                continue
            lines.append(f"[{_toml_str(kind)}]")
            lines.append(f'repo    = {_toml_str(meta.get("repo", ""))}')
            excl = meta.get("exclude", [])
            lines.append(f"exclude = {_toml_list(excl)}")
            lines.append("")
            continue
        for name in sorted(names):
            meta = names[name]
            header = _toml_str(f"{kind}::{name}")
            lines.append(f"[{header}]")
            lines.append(f'repo    = {_toml_str(meta.get("repo", ""))}')
            excl = meta.get("exclude", [])
            lines.append(f"exclude = {_toml_list(excl)}")
            lines.append("")
    return "\n".join(lines)


def _toml_str(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    inner = ", ".join(_toml_str(i) for i in items)
    return f"[{inner}]"
