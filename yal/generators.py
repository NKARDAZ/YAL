"""
Генераторы значений для синтаксиса ${...} в yal.template.toml,
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
from typing import Callable

# ─── реестр генераторов ───────────────────────────────────────────────────────

_REGISTRY: dict[str, Callable[[], str]] = {}

# ${NAME} — генераторы (имя в верхнем регистре, заглушаем $)
_EXPR_RE = re.compile(r'^\$\{([^}]+)\}$')
# ${NAME} внутри строки (не обязательно вся строка)
_GEN_PART_RE = re.compile(r'\$\{([^}]+)\}')
# {field-name} — ссылки на поля пользовательского ввода (строчные, дефисы OK)
_INTERP_PART_RE = re.compile(r'\{([^}]+)\}')


def register(name: str) -> Callable[[Callable[[], str]], Callable[[], str]]:
    """Декоратор для регистрации генератора под именем name."""
    def decorator(fn: Callable[[], str]) -> Callable[[], str]:
        _REGISTRY[name.upper()] = fn
        return fn
    return decorator


# ─── встроенные генераторы ────────────────────────────────────────────────────

@register("UUID")
def _gen_uuid() -> str:
    """Генерирует UUID4 в стандартном формате: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx."""
    return str(uuid.uuid4())


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


# ─── публичный API ────────────────────────────────────────────────────────────

def is_expression(value: str) -> bool:
    """Возвращает True, если value — чистое выражение вида ${...}."""
    return bool(_EXPR_RE.match(value))


def has_interpolation(value: str) -> bool:
    """Возвращает True, если value содержит хотя бы одну вставку {field-name}."""
    return bool(_INTERP_PART_RE.search(value))


def resolve(value: str, fields: dict[str, str] | None = None) -> str | None:
    """
    Вычисляет value и возвращает итоговую строку (или None если результат пустой).

    Порядок обработки:
      1. Если value — чистое ${NAME}: вызывает генератор.
         Неизвестное имя → возвращает исходную строку (не ломаем шаблон).
      2. Если value содержит {field-name} или ${NAME} как часть строки:
         - сначала подставляются генераторы ${NAME},
         - затем поля {field-name} из fields.
         Отсутствующее или пустое поле → заменяется на "".
         Если после всех подстановок остался только статичный текст без
         каких-либо значимых вставок (все поля были пустыми/отсутствующими
         и генераторов не было) — возвращает None.
      3. Иначе: возвращает value как есть.

    Примеры:
        resolve("${UUID}")                                    → "550e8400-…"
        resolve("${DATE}")                                    → "2026-01-15"
        resolve("© {book-author}", {"book-author": "Иван"})  → "© Иван"
        resolve("© {book-author}", {"book-author": ""})      → None
        resolve("{a} и {b}", {"a": "X", "b": ""})            → "X и "
        resolve("{book-title}, ${DATE}", {...})               → "Моя книга, 2026-01-15"
        resolve("plain string")                               → "plain string"
    """
    # ── 1. Чистый генератор ${NAME} ───────────────────────────────────────────
    m = _EXPR_RE.match(value)
    if m:
        name = m.group(1).upper()
        fn = _REGISTRY.get(name)
        if fn is None:
            return value  # неизвестный — возвращаем как есть
        return fn()

    # ── 2. Смешанная строка с ${...} и/или {field-name} ──────────────────────
    has_gen = _GEN_PART_RE.search(value)
    has_field = _INTERP_PART_RE.search(value)

    if has_gen or has_field:
        resolved_fields = fields or {}
        any_substituted = False  # хоть одна вставка дала непустой результат

        # Сначала раскрываем генераторы ${NAME}, чтобы $ не мешал {}-парсингу
        def _sub_gen(match: re.Match) -> str:
            nonlocal any_substituted
            name = match.group(1).upper()
            fn = _REGISTRY.get(name)
            if fn is None:
                # Неизвестный генератор — оставляем как есть, но считаем вставкой:
                # автор явно написал ${...}, значит строка намеренная.
                any_substituted = True
                return match.group(0)
            result = fn()
            any_substituted = True
            return result

        step1 = _GEN_PART_RE.sub(_sub_gen, value)

        # Затем раскрываем поля {field-name}
        def _sub_field(match: re.Match) -> str:
            nonlocal any_substituted
            field_val = resolved_fields.get(match.group(1), "")
            if field_val:
                any_substituted = True
            return field_val

        result = _INTERP_PART_RE.sub(_sub_field, step1)

        # Если ни одна вставка не дала значения — смысла писать нет
        return result if any_substituted else None

    # ── 3. Простой литерал ────────────────────────────────────────────────────
    return value


def known_generators() -> list[str]:
    """Возвращает отсортированный список зарегистрированных имён."""
    return sorted(_REGISTRY.keys())
