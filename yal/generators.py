"""
Генераторы значений для синтаксиса ${...} в .yal/template.toml,
а также интерполяция полей через синтаксис {field-name}.

Используются в поле value маппингов targets.fields:

    [[targets.fields]]
    value = "${UUID}"
    key   = "book.uuid"

    [[targets.fields]]
    value = "${DATE}"
    key   = "meta.created"

    [[targets.fields]]
    value = "${TIMESTAMP}"
    key   = "meta.ts"

    [[targets.fields]]
    value = "${RANDOM}"
    key   = "meta.seed"

    # Интерполяция: {name} — ссылка на поле из [[fields]]
    [[targets.fields]]
    value = "© {book-author}"
    key   = "book.copyright"

    # Смешанный вариант: генератор и поле вместе
    [[targets.fields]]
    value = "{book-title} — {book-author}, ${DATE}"
    key   = "meta.description"

Добавление нового генератора: зарегистрировать функцию в _REGISTRY
через декоратор @register или добавить запись вручную.
"""

from __future__ import annotations

import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Union

# ─── реестр генераторов ───────────────────────────────────────────────────────

_REGISTRY: dict[str, Callable[[], Union[str, int]]] = {}

# ${NAME} — генераторы (имя в верхнем регистре, заглушаем $)
_EXPR_RE = re.compile(r'^\$\{([^}]+)\}$')
# ${NAME} внутри строки (не обязательно вся строка)
_GEN_PART_RE = re.compile(r'\$\{([^}]+)\}')
# {field-name} — ссылки на поля пользовательского ввода (строчные, дефисы OK)
_INTERP_PART_RE = re.compile(r'\{([^}]+)\}')


def register(name: str) -> Callable[[Callable[[], Union[str, int]]], Callable[[], Union[str, int]]]:
    """Декоратор для регистрации генератора под именем name."""
    def decorator(fn: Callable[[], Union[str, int]]) -> Callable[[], Union[str, int]]:
        _REGISTRY[name.upper()] = fn
        return fn
    return decorator


# ─── встроенные генераторы ────────────────────────────────────────────────────

@register("UUID")
def _gen_uuid() -> str:
    """Генерирует UUID4 в стандартном формате: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx."""
    return str(uuid.uuid4())


@register("YEAR")
def _gen_year() -> int:
    """Текущий год (UTC)."""
    return datetime.now(timezone.utc).year


@register("MONTH")
def _gen_month() -> int:
    """Текущий месяц (UTC)."""
    return datetime.now(timezone.utc).month


@register("DAY")
def _gen_day() -> int:
    """Текущий день (UTC)."""
    return datetime.now(timezone.utc).day


@register("DATE")
def _gen_date() -> str:
    """Текущая дата в формате YYYY-MM-DD (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@register("TIMESTAMP")
def _gen_timestamp() -> str:
    """Unix timestamp в секундах (целое число, UTC)."""
    return str(int(datetime.now(timezone.utc).timestamp()))


@register("RANDOM")
def _gen_random() -> str:
    """Случайное целое число от 0 до 2^31 − 1."""
    return str(random.randint(0, 2**31 - 1))


@register("NULL")
def _gen_null() -> str:
    return "__YAL_NULL__"


# ─── публичный API ────────────────────────────────────────────────────────────

def is_expression(value: str) -> bool:
    """Возвращает True, если value — чистое выражение вида ${...}."""
    return bool(_EXPR_RE.match(value))


def has_interpolation(value: str) -> bool:
    """Возвращает True, если value содержит хотя бы одну вставку {field-name}."""
    return bool(_INTERP_PART_RE.search(value))


def resolve(value: str, fields: dict[str, str] | None = None) -> str | int | None:
    # ── 1. Чистый генератор ${NAME} ───────────────────────────────────────────
    m = _EXPR_RE.match(value)
    if m:
        name = m.group(1).upper()
        fn = _REGISTRY.get(name)
        if fn is None:
            return value
        return fn()  # Возвращаем результат как есть (int или str)

    # ── 2. Смешанная строка ────────────────────────────────────────────────────
    # Если в строке есть хоть что-то еще, кроме генератора,
    # результат ВСЕГДА будет строкой (так как мы конкатенируем текст)

    has_gen = _GEN_PART_RE.search(value)
    has_field = _INTERP_PART_RE.search(value)

    if has_gen or has_field:
        resolved_fields = fields or {}

        # Заменяем генераторы
        def _sub_gen_to_str(match: re.Match) -> str:
            name = match.group(1).upper()
            fn = _REGISTRY.get(name)
            # Если генератор не найден, оставляем ${NAME} как текст
            return str(fn()) if fn else match.group(0)

        step1 = _GEN_PART_RE.sub(_sub_gen_to_str, value)

        # Заменяем поля
        result = _INTERP_PART_RE.sub(lambda m: to_str(resolved_fields.get(m.group(1), "")), step1)

        # Если после всех замен строка пуста, возвращаем None
        return result if result else None

    # ── 3. Простой литерал ────────────────────────────────────────────────────
    return value


def known_generators() -> list[str]:
    """Возвращает отсортированный список зарегистрированных имён."""
    return sorted(_REGISTRY.keys())


def to_str(value: Any) -> str:
    """
    Приводит произвольное значение поля к строке: используется и при
    интерполяции {field-name} (resolve() ниже строит результат через
    re.sub, который требует строку), и в template_config.py — при
    нормализации FieldDef.default (TOML может хранить его как нативный
    bool/array, а не строку) и при записи булевых/multi-select полей
    в .env (там значения всегда плоские строки).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value)
