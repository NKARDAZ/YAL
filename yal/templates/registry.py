"""
Реестр шаблонов.

Каждая запись описывает один именованный шаблон внутри типа.
Структура записи:
  {
    "repo":    str,        # ссылка на GitHub-репозиторий
    "exclude": list[str],  # файлы/папки, которые не копируются при create
    "is_user": bool,       # True → пользовательский шаблон (user_store)
  }

BOOK_REGISTRY["default"] — шаблон, используемый при `yal create book`
                            (без указания :name).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TemplateEntry:
    repo: str
    exclude: list[str] = field(default_factory=list)
    is_user: bool = False   # True для шаблонов из user_registry


# ── Реестр шаблонов для типа "book" ──────────────────────────────────────────

BOOK_REGISTRY: dict[str, TemplateEntry] = {
    "default": TemplateEntry(
        repo="https://github.com/DemerNkardaz/Typst-Book-Template",
        exclude=["README.md", "LICENSE", "TODO.md", "yal.template.toml"],
    ),
}

# ── Общий реестр: тип → его реестр шаблонов ──────────────────────────────────

KIND_REGISTRIES: dict[str, dict[str, TemplateEntry]] = {
    "book": BOOK_REGISTRY,
}


def get_entry(kind: str, name: str) -> TemplateEntry:
    """
    Вернуть запись реестра для (kind, name).
    kind всегда lowercase. name сравнивается без учёта регистра,
    но в хранилище и meta.json остаётся оригинальный регистр.
    Бросает ValueError если не найдено.
    """
    # 1. Встроенный реестр (case-insensitive по name)
    registry = KIND_REGISTRIES.get(kind)
    if registry is not None:
        entry = _iget(registry, name)
        if entry is not None:
            return entry

    # 2. Пользовательский реестр
    from yal.templates import user_registry as _ur
    user_entry = _ur.get_entry(kind, name)
    if user_entry is not None:
        return user_entry

    # 3. Понятное сообщение об ошибке
    builtin_names = list((registry or {}).keys())
    user_names = _ur.list_names(kind)
    available = ", ".join(sorted(set(builtin_names + user_names))) or "—"

    if registry is None and not user_names:
        available_kinds = ", ".join(list_kinds() + _ur.list_kinds())
        raise ValueError(f"Неизвестный тип: '{kind}'. Доступные: {available_kinds or '—'}")

    raise ValueError(
        f"Шаблон '{name}' не найден для '{kind}'. Доступные: {available}"
    )


def _iget(d: dict[str, TemplateEntry], name: str) -> TemplateEntry | None:
    """Case-insensitive dict lookup."""
    name_lower = name.lower()
    for key, val in d.items():
        if key.lower() == name_lower:
            return val
    return None


def list_kinds() -> list[str]:
    return sorted(KIND_REGISTRIES.keys())


def list_names(kind: str) -> list[str]:
    registry = KIND_REGISTRIES.get(kind, {})
    return sorted(registry.keys())
