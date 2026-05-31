"""
Реестр обработчиков и точка входа для разрешения kind → handler.

HANDLERS содержит явно объявленные встроенные обработчики.
Если kind не найден там, но существует в пользовательском реестре
(user-templates.toml) — возвращается GenericHandler для этого kind.
Если kind не найден нигде — возвращается None, и вызывающий код
должен вывести ошибку.
"""

from __future__ import annotations

from yal.templates.handler import GenericHandler
from yal.templates.registry import TemplateEntry

HANDLERS: dict[str, GenericHandler] = {
    "book": GenericHandler("book"),
}


def get_handler(kind: str, entry: TemplateEntry | None = None) -> GenericHandler | None:
    """
    Возвращает обработчик для kind или None если kind неизвестен.

    Порядок поиска:
      1. Явно объявленный в HANDLERS — возвращаем его.
      2. entry.is_user=True (kind из user-templates.toml) — GenericHandler(kind).
      3. Иначе — None (неизвестный kind, нужно вывести ошибку).
    """
    handler = HANDLERS.get(kind)
    if handler is not None:
        return handler

    if entry is not None and entry.is_user:
        return GenericHandler(kind)

    return None


def known_kinds() -> list[str]:
    """
    Возвращает объединённый список известных kind:
    встроенные из HANDLERS + пользовательские из user-templates.toml.
    Используется для формирования сообщений об ошибках.
    """
    from yal.templates import user_registry
    builtin = list(HANDLERS.keys())
    user = user_registry.list_kinds()
    return sorted(set(builtin + user))
