"""
Реестр шаблонов.

Каждая запись описывает один именованный шаблон внутри типа.
Структура записи:
  {
    "repo":    str,        # ссылка на GitHub-репозиторий
    "exclude": list[str],  # файлы/папки, которые не копируются при create
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


# ── Реестр шаблонов для типа "book" ──────────────────────────────────────────

BOOK_REGISTRY: dict[str, TemplateEntry] = {
    "default": TemplateEntry(
        repo="https://github.com/DemerNkardaz/Typst-Book-Template",
        exclude=["README.md", "LICENSE", "TODO.md", "yal.toml"],
    ),
}

# ── Общий реестр: тип → его реестр шаблонов ──────────────────────────────────
# При добавлении нового типа достаточно добавить его сюда.

KIND_REGISTRIES: dict[str, dict[str, TemplateEntry]] = {
    "book": BOOK_REGISTRY,
}


def get_entry(kind: str, name: str) -> TemplateEntry:
    """
    Вернуть запись реестра для (kind, name).
    Бросает ValueError с понятным сообщением если не найдено.
    """
    registry = KIND_REGISTRIES.get(kind)
    if registry is None:
        available = ", ".join(KIND_REGISTRIES.keys())
        raise ValueError(f"Неизвестный тип: '{kind}'. Доступные: {available}")

    entry = registry.get(name)
    if entry is None:
        available = ", ".join(registry.keys())
        raise ValueError(
            f"Шаблон '{name}' не найден для '{kind}'. Доступные: {available}"
        )

    return entry


def list_kinds() -> list[str]:
    return sorted(KIND_REGISTRIES.keys())


def list_names(kind: str) -> list[str]:
    registry = KIND_REGISTRIES.get(kind, {})
    return sorted(registry.keys())
